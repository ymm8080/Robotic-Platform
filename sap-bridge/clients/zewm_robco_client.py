"""Self-contained HTTP client for ZEWM_ROBCO_SRV OData service.

Provides typed Python access to the SAP EWM ZEWM_ROBCO_SRV function imports
used by the EWM Cloud Robotics integration (SAP/ewm-cloud-robotics).

Usage::

    from clients.zewm_robco_client import ZewmRobcoClient

    client = ZewmRobcoClient(config)
    result = client.get_new_robot_who("WH01", "MIR_001")
    client.close()

Auth modes:
  - **basic** (default): Basic Auth + CSRF token (legacy SAP EWM)
  - **oauth2**: OAuth2 client_credentials + Bearer token (S/4HANA 2023+)

Reference:
  SAP/ewm-cloud-robotics (Apache 2.0)
  d:/ewm robot/reference/design all/implementation plan/
  backends/ewm_backend.py (CSRF, auth, rate-limit patterns)
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from typing import Any

import httpx
import redis as rd

from auth import OAuth2TokenManager, read_client_secret
from redis_client import redis_from_url

from .zewm_robco_exceptions import (
    RobcoInternalError,
    raise_for_error_code,
)

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────

DEFAULT_BASE_URL = os.getenv(
    "SAP_EWM_BASE_URL", os.getenv("SAP_BASE_URL", "http://sap-ewm:8000"),
)
DEFAULT_CLIENT = os.getenv("SAP_CLIENT", "100")
DEFAULT_USER = os.getenv("SAP_USER", "")
DEFAULT_PASSWORD_FILE = os.getenv(
    "SAP_PASSWORD_FILE", "/run/secrets/sap_password",
)
DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

DEFAULT_ODATA_SERVICE = "/sap/opu/odata/sap/ZEWM_ROBCO_SRV"

MAX_REQUESTS_PER_MINUTE = 80
TOKEN_BUCKET_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE
CSRF_REFRESH_INTERVAL = 1500  # 25 minutes
_CSRF_REDIS_KEY = "sap:zewm_robco:csrf_token"
_CSRF_REDIS_COOKIE_KEY = "sap:zewm_robco:csrf_cookies"
_CSRF_REDIS_REFRESH_KEY = "sap:zewm_robco:csrf_last_refresh"
_CONFIRM_RETRY_MAX = 5
_CONFIRM_RETRY_BACKOFF_BASE = 1.0
_CONFIRM_RETRY_BACKOFF_CAP = 30.0
# Max HTTP retries for 401/403/429 in a single _request() call
_MAX_HTTP_RETRIES = 3


def _read_password(password_file: str) -> str:
    """Read password from a Docker secret file."""
    try:
        with open(password_file, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("Password file not found at configured path: %s", password_file)
        raise


# ── CSRF Token Manager ────────────────────────────────────────────────


class _ZewmCsrfManager:
    """CSRF token manager for ZEWM_ROBCO_SRV with Redis caching.

    Follows the same pattern as ``CsrfTokenManager`` in ``backends/ewm_backend.py``
    but uses a dedicated Redis key namespace to avoid collisions.
    """

    def __init__(
        self,
        redis_client: rd.Redis,
        auth: tuple[str, str] | None = None,
    ):
        self._redis = redis_client
        self._auth = auth

    def get_token(self) -> tuple[str, str] | None:
        """Return cached (token, cookies) or None."""
        token = self._redis.get(_CSRF_REDIS_KEY)
        cookies = self._redis.get(_CSRF_REDIS_COOKIE_KEY)
        if token and cookies:
            return (token, cookies)
        return None

    def set_token(self, token: str, cookies: str) -> None:
        """Cache CSRF token and cookies in Redis."""
        pipe = self._redis.pipeline()
        pipe.setex(_CSRF_REDIS_KEY, CSRF_REFRESH_INTERVAL, token)
        pipe.setex(_CSRF_REDIS_COOKIE_KEY, CSRF_REFRESH_INTERVAL, cookies)
        pipe.set(_CSRF_REDIS_REFRESH_KEY, str(time.time()))
        pipe.execute()

    def fetch_new(
        self,
        client: httpx.Client,
        base_url: str,
        odata_service: str,
        *,
        auth_headers: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Fetch a fresh CSRF token from SAP via $metadata.

        Args:
            client: httpx client for the HTTP request.
            base_url: SAP base URL.
            odata_service: OData service path.
            auth_headers: Optional auth headers (e.g. OAuth2 Bearer token).
                For Basic auth, credentials are passed via ``self._auth``.
        """
        url = f"{base_url}{odata_service}/$metadata"
        headers = {"X-CSRF-Token": "Fetch", **(auth_headers or {})}
        resp = client.get(url, headers=headers, auth=self._auth)
        resp.raise_for_status()
        token = resp.headers.get("X-CSRF-Token", "")
        if not token:
            raise RuntimeError(
                f"SAP did not return X-CSRF-Token header (status {resp.status_code})",
            )
        cookies = "; ".join(f"{c.name}={c.value}" for c in resp.cookies)
        self.set_token(token, cookies)
        logger.info("Fetched new ZEWM_ROBCO CSRF token")
        return token, cookies

    def invalidate(self) -> None:
        """Invalidate cached CSRF token and cookies."""
        self._redis.delete(_CSRF_REDIS_KEY)
        self._redis.delete(_CSRF_REDIS_COOKIE_KEY)
        logger.info("CSRF token cache invalidated")

    def close(self) -> None:
        """No-op — Redis connection is owned by the parent ZewmRobcoClient."""
        pass


# ── Client ─────────────────────────────────────────────────────────────


class ZewmRobcoClient:
    """HTTP client for the SAP ZEWM_ROBCO_SRV OData service.

    Provides P0/P1 methods for robot-WHO assignment, warehouse task
    confirmation (two-step), status setting, and lookup queries.

    Config keys:
        enabled (bool): Whether this client is enabled.
        base_url (str): SAP EWM base URL.
        client (str): SAP client (e.g. ``"100"``).
        odata_service (str): OData service path override.
        auth_mode (str): ``"basic"`` or ``"oauth2"``.
        user (str): Basic auth username.
        password_file (str): Docker secret path for password.
        password (str): Inline password (overrides password_file).
        rate_limit (int): Max requests per minute.
        connection_timeout (int): HTTP timeout in seconds.
        redis_url (str): Redis connection URL.
        confirm_retry_max (int): Max retries for task confirmation.
        confirm_retry_backoff_base (float): Backoff multiplier.
        confirm_retry_backoff_cap (float): Max backoff seconds.
        oauth2.token_url (str): OAuth2 token endpoint.
        oauth2.client_id (str): OAuth2 client ID.
        oauth2.client_secret_file (str): OAuth2 client secret file path.
        oauth2.scope (str): OAuth2 scope.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._cfg = config or {}
        self._enabled = bool(self._cfg.get("enabled", True))
        self._base_url = self._cfg.get("base_url", DEFAULT_BASE_URL).rstrip("/")
        self._client = self._cfg.get("client", DEFAULT_CLIENT)
        self._odata_service = self._cfg.get("odata_service", DEFAULT_ODATA_SERVICE)
        self._rate_limit = int(self._cfg.get("rate_limit", MAX_REQUESTS_PER_MINUTE))
        self._token_interval = 60.0 / self._rate_limit
        self._connection_timeout = int(self._cfg.get("connection_timeout", 30))
        self._redis_url = self._cfg.get("redis_url", DEFAULT_REDIS_URL)

        # Confirm retry settings
        self._confirm_retry_max = int(
            self._cfg.get("confirm_retry_max", _CONFIRM_RETRY_MAX),
        )
        self._confirm_retry_backoff_base = float(
            self._cfg.get("confirm_retry_backoff_base", _CONFIRM_RETRY_BACKOFF_BASE),
        )
        self._confirm_retry_backoff_cap = float(
            self._cfg.get("confirm_retry_backoff_cap", _CONFIRM_RETRY_BACKOFF_CAP),
        )

        # Auth mode: "basic" (default) or "oauth2"
        self._auth_mode = self._cfg.get("auth_mode", "basic")
        self._auth: tuple[str, str] | None = None
        self._oauth2: OAuth2TokenManager | None = None
        self._oauth2_cfg: dict[str, str] = {}

        # Lazy-init references
        self._redis: rd.Redis | None = None
        self._csrf: _ZewmCsrfManager | None = None
        self._last_request_time: float = 0.0

        if self._auth_mode == "oauth2":
            self._init_oauth2()
        else:
            self._init_basic_auth()

    # ── Auth init ─────────────────────────────────────────────────────

    def _init_basic_auth(self) -> None:
        """Initialize Basic Auth credentials."""
        user = self._cfg.get("user", DEFAULT_USER)
        pw_file = self._cfg.get("password_file", DEFAULT_PASSWORD_FILE)
        password = self._cfg.get("password") or _read_password(pw_file)
        self._auth = (user, password) if user else None

    def _init_oauth2(self) -> None:
        """Initialize OAuth2 client_credentials config."""
        oauth2_cfg = self._cfg.get("oauth2", {})
        token_url = oauth2_cfg.get("token_url", "")
        client_id = oauth2_cfg.get("client_id", "")

        if not token_url or not client_id:
            raise ValueError(
                "OAuth2 auth_mode requires oauth2.token_url and oauth2.client_id",
            )

        secret_file = oauth2_cfg.get(
            "client_secret_file",
            "/run/secrets/sap_oauth_client_secret",
        )
        client_secret = oauth2_cfg.get("client_secret") or read_client_secret(
            secret_file,
        )
        scope = oauth2_cfg.get("scope", "")

        self._oauth2_cfg = {
            "token_url": token_url,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        }

    # ── Lazy initializers ─────────────────────────────────────────────

    def _ensure_redis(self) -> rd.Redis:
        """Get or create Redis connection (lazy init)."""
        if self._redis is None:
            self._redis = redis_from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    def _ensure_csrf(self) -> _ZewmCsrfManager:
        """Get or create CSRF token manager (lazy init).

        OAuth2 Bearer tokens are NOT fetched here — they are obtained
        on demand when ``fetch_new`` or ``_get_headers`` is called.
        This avoids storing stale tokens and unnecessary HTTP requests
        at initialization time.
        """
        if self._csrf is None:
            self._csrf = _ZewmCsrfManager(
                self._ensure_redis(),
                auth=self._auth,
            )
        return self._csrf

    def _ensure_oauth2(self) -> OAuth2TokenManager:
        """Get or create OAuth2 token manager (lazy init)."""
        if self._oauth2 is None:
            self._oauth2 = OAuth2TokenManager(
                redis_client=self._ensure_redis(),
                **self._oauth2_cfg,
            )
        return self._oauth2

    # ── Rate limiting ─────────────────────────────────────────────────

    def _throttle(self) -> None:
        """Token-bucket rate limiter (simple sleep-based).

        Even when disabled, ``_last_request_time`` is updated so that if
        the client is re-enabled later, the rate limit window is accurate.
        """
        if not self._enabled:
            self._last_request_time = time.time()
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self._token_interval:
            time.sleep(self._token_interval - elapsed)
        self._last_request_time = time.time()

    # ── HTTP helpers ──────────────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        """Create an httpx client with configured timeout and TLS settings."""
        verify_ssl = os.getenv("SAP_VERIFY_SSL", "true").lower() != "false"
        return httpx.Client(timeout=self._connection_timeout, verify=verify_ssl)

    def _get_auth_for_request(self) -> tuple[str, str] | None:
        """Return auth tuple for httpx requests.

        - basic mode: returns ``(user, password)``
        - oauth2 mode: returns ``None`` (Bearer token injected via headers)
        """
        if self._auth_mode == "oauth2":
            return None
        return self._auth

    def _get_auth_headers(self, client: httpx.Client) -> dict[str, str]:
        """Build auth-related headers for OAuth2 mode.

        For Basic mode, returns empty dict (httpx handles via ``auth=`` param).
        """
        if self._auth_mode != "oauth2":
            return {}
        oauth2 = self._ensure_oauth2()
        token = oauth2.get_valid_token(client)
        return {"Authorization": f"Bearer {token}"}

    def _get_base_headers(self, csrf_token: str | None = None) -> dict[str, str]:
        """Build base HTTP headers (no auth) for ZEWM_ROBCO_SRV requests.

        Auth headers (OAuth2 Bearer token) are added separately by
        ``_get_full_headers`` to avoid coupling header construction
        with token retrieval.
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-sap-client": self._client,
        }
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        return headers

    def _get_full_headers(
        self,
        csrf_token: str | None,
        cookies: str | None,
        client: httpx.Client,
    ) -> dict[str, str]:
        """Build complete headers: base + auth + CSRF cookie.

        This is the single place where OAuth2 Bearer tokens are
        injected into request headers, avoiding duplicate token
        fetches that occurred when ``_get_headers`` was called
        multiple times for the same request.
        """
        headers = self._get_base_headers(csrf_token)
        if cookies:
            headers["Cookie"] = cookies
        if self._auth_mode == "oauth2":
            headers.update(self._get_auth_headers(client))
        return headers

    def _get_csrf_headers(self, client: httpx.Client) -> dict[str, str]:
        """Get headers including a valid CSRF token.

        Uses cached token if available, otherwise fetches a new one.
        Auth headers (OAuth2 Bearer token) are obtained on demand
        and passed to ``fetch_new`` for the $metadata request.
        """
        csrf = self._ensure_csrf()
        cached = csrf.get_token()
        if cached:
            token, cookies = cached
            return self._get_full_headers(token, cookies, client)
        auth_hdrs = (
            self._get_auth_headers(client)
            if self._auth_mode == "oauth2"
            else {}
        )
        token, cookies = csrf.fetch_new(
            client, self._base_url, self._odata_service,
            auth_headers=auth_hdrs,
        )
        return self._get_full_headers(token, cookies, client)

    # ── OData URL construction ────────────────────────────────────────

    def _function_import_url(self, name: str, **params: Any) -> str:
        """Build a full OData function-import URL with query parameters.

        SAP ZEWM_ROBCO_SRV uses positional query-string parameters wrapped in
        single quotes. According to SAP OData V2 specification, single quotes
        within parameter values must be escaped by doubling them.

        Example::

            _function_import_url(
                "AssignRobotWho",
                Lgnum="WH01", Rsrc="MIR_001", Who="123",
            )
            # → ".../AssignRobotWho?Lgnum='WH01'&Rsrc='MIR_001'&Who='123'"
            
            _function_import_url(
                "SomeFunction",
                Name="O'Brien",
            )
            # → ".../SomeFunction?Name='O''Brien'"

        Args:
            name: Function import name (e.g. ``"AssignRobotWho"``).
            **params: Query parameters as keyword arguments.

        Returns:
            Full URL string.
        """
        base = f"{self._base_url}{self._odata_service}/{name}"
        if not params:
            return base
        qs_parts = []
        for k, v in params.items():
            if v is not None:
                # Escape single quotes by doubling them (SAP OData V2 specification)
                escaped_value = str(v).replace("'", "''")
                qs_parts.append(f"{k}='{escaped_value}'")
        qs = "&".join(qs_parts)
        return f"{base}?{qs}"

    # ── Response parsing ──────────────────────────────────────────────

    @staticmethod
    def parse_response(resp: httpx.Response) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Unwrap SAP OData V2 ``{"d": {...}}`` envelope.

        SAP NetWeaver Gateway wraps responses in a ``d`` key:
        - Single entity: ``{"d": {"Who": "123"}}`` → ``{"Who": "123"}``
        - Collection: ``{"d": {"results": [...]}}`` → ``[...]``
        - Single-item collection: ``{"d": {"results": {...}}}`` → ``[{...}]`` (wrapped in list)

        When the ``d`` object contains a ``results`` key (SAP collection
        convention), the method returns:
        - ``list[dict]`` if ``results`` is a list
        - ``[dict]`` (single-element list) if ``results`` is a dict
        - raises ``RobcoInternalError`` for other types

        Callers should check the return type (``list`` vs ``dict``) when
        expecting collection responses.

        Args:
            resp: The httpx response object.

        Returns:
            - ``dict`` for single-entity responses.
            - ``list[dict]`` for collection responses (including single-item collections).
            - ``None`` if ``d`` is null or response is empty.

        Raises:
            RobcoInternalError: If response format is unexpected (non-dict, non-list)
        """
        if resp.status_code == 204 or not resp.text.strip():
            return None
        try:
            body = resp.json()
        except Exception as e:
            from .zewm_robco_exceptions import RobcoInternalError
            raise RobcoInternalError(f"Failed to parse response as JSON: {e}")

        d = body.get("d", body)
        if d is None:
            return None

        # Handle different response types
        if isinstance(d, dict):
            # SAP OData V2 collection convention: d.results contains collection data
            if "results" in d:
                results = d["results"]
                if isinstance(results, list):
                    # Normal collection response
                    return results
                elif isinstance(results, dict):
                    # Single-item collection wrapped in a dict
                    # Wrap it in a list for consistent return type
                    return [results]
                else:
                    # Unexpected results type (should not happen)
                    from .zewm_robco_exceptions import RobcoInternalError
                    raise RobcoInternalError(
                        f"Unexpected 'results' type in response: {type(results).__name__}"
                    )
            # Return the dict as-is (single entity response)
            return d
        elif isinstance(d, list):
            # Handle case where 'd' is directly a list (non-standard but possible)
            return d
        else:
            # d is a primitive type (string, number, boolean, etc.)
            # Wrap it in a dict with a '_value' key for consistency
            return {"_value": d}

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Parse SAP error JSON and raise the matching typed exception.

        SAP error format::

            {"error": {"code": "ROBOT_NOT_FOUND/001",
                        "message": {"lang": "en", "value": "Resource ..."}}}

        The numeric suffix (``/NNN``) is stripped before dispatching
        to ``raise_for_error_code()``.

        Args:
            resp: The httpx response object with an error status code.

        Raises:
            The appropriate ``RobcoError`` subclass.
        """
        try:
            body = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise RobcoInternalError(
                f"HTTP {resp.status_code}: non-JSON response: {resp.text[:200]}",
            )
        try:
            err = body.get("error", {})
            raw_code = err.get("code", "INTERNAL_ERROR")
            # Strip SAP's "/NNN" numeric suffix
            error_code = raw_code.split("/")[0]
            detail = err.get("message", {}).get("value", "")
            raise_for_error_code(error_code, detail)
        except KeyError:
            raise RobcoInternalError(
                f"HTTP {resp.status_code}: unexpected error format: {body}",
            )

    def _prepare_retry_headers(
        self, status_code: int, client: httpx.Client,
    ) -> dict[str, str]:
        """Build fresh headers for a retry after a transient failure.

        Centralises the header preparation logic for 403/401/429 retries
        to avoid code duplication between retry paths.

        - **403**: CSRF token expired — fetch a new CSRF token.
        - **401**: OAuth2 token expired — invalidated by caller; a fresh
          token will be obtained via ``_get_csrf_headers``.
        - **429**: Rate limited — CSRF was invalidated by caller; a fresh
          token will be obtained via ``_get_csrf_headers``.

        Args:
            status_code: The HTTP status code that triggered the retry.
            client: A fresh httpx.Client for any token fetch requests.

        Returns:
            Complete headers dict for the retry request.
        """
        # For 403, we need to fetch a new CSRF token
        if status_code == 403:
            csrf = self._ensure_csrf()
            # In OAuth2 mode, we need auth headers for the CSRF token fetch
            auth_hdrs = (
                self._get_auth_headers(client)
                if self._auth_mode == "oauth2"
                else {}
            )
            try:
                token, cookies = csrf.fetch_new(
                    client,
                    self._base_url,
                    self._odata_service,
                    auth_headers=auth_hdrs,
                )
                return self._get_full_headers(token, cookies, client)
            except Exception as exc:
                # If CSRF fetch fails (e.g., due to OAuth2 token fetch failure),
                # propagate the exception so retry can fail gracefully
                logger.error(
                    "Failed to fetch new CSRF token for 403 retry: %s",
                    exc
                )
                raise

        # For 401 (OAuth2) or 429 — get fresh headers including CSRF token
        # Note: OAuth2 token invalidation is done in _request before calling this
        return self._get_csrf_headers(client)

    # ── Request retry helper ──────────────────────────────────────────────

    def _execute_with_retry(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        initial_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Execute HTTP request with retry logic for transient failures.
        
        Centralizes retry logic for 403 (CSRF expiry), 401 (OAuth2 expiry),
        and 429 (rate limiting) responses.
        
        Args:
            method: HTTP method.
            url: Full URL.
            body: Optional request body.
            initial_headers: Initial headers for first attempt.
            
        Returns:
            HTTP response.
        """
        client = self._get_client()
        try:
            headers = initial_headers or self._get_csrf_headers(client)
            resp = client.request(
                method=method,
                url=url,
                json=body,
                headers=headers,
                auth=self._get_auth_for_request(),
            )

            retries = 0
            while (
                resp.status_code in (401, 403, 429)
                and retries < _MAX_HTTP_RETRIES
            ):
                # Pre-retry actions based on status code
                if resp.status_code == 403:
                    logger.info("CSRF token expired, refreshing...")
                elif resp.status_code == 401 and self._auth_mode == "oauth2":
                    logger.info("OAuth2 token may be expired, invalidating...")
                    self._ensure_oauth2().invalidate()
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2))
                    delay = min(retry_after, 30)
                    logger.warning("SAP rate limited — backing off %ds", delay)
                    time.sleep(delay)
                    # Invalidate CSRF cache to force fresh token after backoff
                    self._ensure_csrf().invalidate()
                else:
                    # 401 in basic mode — not retryable
                    break

                # Create a new client for retry to ensure clean connection state
                with contextlib.suppress(Exception):
                    client.close()
                client = self._get_client()

                # Prepare headers for retry (with exception handling)
                try:
                    headers = self._prepare_retry_headers(
                        resp.status_code, client,
                    )
                except Exception as exc:
                    logger.error(
                        "Retry header preparation failed (status=%d): %s",
                        resp.status_code, exc,
                    )
                    raise

                resp = client.request(
                    method=method,
                    url=url,
                    json=body,
                    headers=headers,
                    auth=self._get_auth_for_request(),
                )
                retries += 1

                # If we still have an error status after max retries, break to avoid infinite loop
                if retries >= _MAX_HTTP_RETRIES and resp.status_code in (401, 403, 429):
                    logger.error(
                        "Max retries (%d) reached for status %d, giving up",
                        _MAX_HTTP_RETRIES, resp.status_code,
                    )
                    break

            return resp
        finally:
            with contextlib.suppress(Exception):
                client.close()

    # ── Core request method ───────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with CSRF retry and error handling.

        This is the central request dispatcher.  On CSRF expiry (403),
        OAuth2 token expiry (401), or rate limiting (429), it refreshes
        credentials and retries up to ``_MAX_HTTP_RETRIES`` times.
        A new ``httpx.Client`` is created for each retry to ensure clean
        connection state.  SAP error responses are parsed via
        ``_handle_error_response()``.

        Args:
            method: HTTP method (``"GET"``, ``"POST"``, etc.).
            path: URL path (relative or absolute).
            body: Optional JSON-serializable request body.

        Returns:
            The parsed response dict (unwrapped from SAP envelope).

        Raises:
            RobcoError subclass on SAP error.
        """
        self._throttle()

        full_url = (
            f"{self._base_url}{path}"
            if not path.startswith("http")
            else path
        )

        resp = self._execute_with_retry(method, full_url, body)

        # Success paths
        if resp.status_code in (200, 201, 204):
            if resp.status_code == 204 or not resp.text.strip():
                return {}
            return self.parse_response(resp)

        # Error path
        self._handle_error_response(resp)
        # Should not reach here, but satisfy the type checker
        return {}  # pragma: no cover

    # ═══════════════════════════════════════════════════════════════════
    # P0 Methods — Critical for robot operation
    # ═══════════════════════════════════════════════════════════════════

    # ── P0: assign_robot_who ──────────────────────────────────────────

    def assign_robot_who(
        self,
        lgnum: str,
        rsrc: str,
        who: str,
    ) -> dict[str, Any]:
        """Assign a warehouse order to a robot resource. [P0]

        Calls ``AssignRobotWho`` function import (POST).

        Args:
            lgnum: Warehouse number (e.g. ``"WH01"``).
            rsrc: Robot resource ID (e.g. ``"MIR_001"``).
            who: Warehouse order number.

        Returns:
            SAP response dict (usually the assigned WHO header data).

        Raises:
            WhoNotFoundError: WHO does not exist.
            WhoLockedError: WHO is locked.
            WhoAssignedError: WHO already assigned.
            RobotNotFoundError: Robot resource not found.
        """
        url = self._function_import_url(
            "AssignRobotWho",
            Lgnum=lgnum,
            Rsrc=rsrc,
            Who=who,
        )
        return self._request("POST", url)

    # ── P0: confirm_task_step_1 ───────────────────────────────────────

    def confirm_task_step_1(
        self,
        lgnum: str,
        tanum: str,
        rsrc: str,
    ) -> dict[str, Any]:
        """First step of two-step warehouse task confirmation. [P0]

        Calls ``ConfirmWarehouseTaskStep1`` function import (POST).
        Associates the resource with the warehouse task in SAP EWM.

        Args:
            lgnum: Warehouse number.
            tanum: Warehouse task number.
            rsrc: Robot resource ID.

        Returns:
            SAP response dict.

        Raises:
            WhtAssignedError: Task already assigned.
            RobotNotFoundError: Robot resource not found.
        """
        url = self._function_import_url(
            "ConfirmWarehouseTaskStep1",
            Lgnum=lgnum,
            Tanum=tanum,
            Rsrc=rsrc,
        )
        return self._request("POST", url)

    # ── P0: confirm_task ──────────────────────────────────────────────

    def confirm_task(
        self,
        lgnum: str,
        tanum: str,
        nista: str,
        rsrc: str,
        *,
        altme: str | None = None,
        nlpla: str | None = None,
        nlenr: str | None = None,
        parti: str | None = None,
        conf_exc: str | None = None,
    ) -> dict[str, Any]:
        """Final step of warehouse task confirmation. [P0]

        Calls ``ConfirmWarehouseTask`` function import (POST).
        Completes the warehouse task with actual quantities, bins, HUs,
        and optional exception codes.

        Args:
            lgnum: Warehouse number.
            tanum: Warehouse task number.
            nista: Activity (e.g. ``"PICK"``, ``"PUT"``).
            rsrc: Robot resource ID.
            altme: Alternative unit of measure.
            nlpla: Destination storage bin override.
            nlenr: Destination storage type override.
            parti: Confirmation partial quantity.
            conf_exc: Exception code (see ``ExceptionCode`` enum).

        Returns:
            SAP response dict.

        Raises:
            WhtNotConfirmedError: Task could not be confirmed.
            WhtAlreadyConfirmedError: Task already confirmed.
            StatusNotSetError: Robot status not set.
        """
        url = self._function_import_url(
            "ConfirmWarehouseTask",
            Lgnum=lgnum,
            Tanum=tanum,
            Nista=nista,
            Rsrc=rsrc,
            Altme=altme,
            Nlpla=nlpla,
            Nlenr=nlenr,
            Parti=parti,
            ConfExc=conf_exc,
        )
        return self._request("POST", url)

    # ── P0: unassign_robot_who ────────────────────────────────────────

    def unassign_robot_who(
        self,
        lgnum: str,
        rsrc: str,
        who: str,
    ) -> dict[str, Any]:
        """Unassign a warehouse order from a robot resource. [P0]

        Calls ``UnassignRobotWho`` function import (POST).

        Args:
            lgnum: Warehouse number.
            rsrc: Robot resource ID.
            who: Warehouse order number.

        Returns:
            SAP response dict.

        Raises:
            WhoNotUnassignedError: WHO could not be unassigned.
            WhoNotFoundError: WHO does not exist.
        """
        url = self._function_import_url(
            "UnassignRobotWho",
            Lgnum=lgnum,
            Rsrc=rsrc,
            Who=who,
        )
        return self._request("POST", url)

    # ═══════════════════════════════════════════════════════════════════
    # P1 Methods — Standard queries and status operations
    # ═══════════════════════════════════════════════════════════════════

    # ── P1: get_new_robot_who ─────────────────────────────────────────

    def get_new_robot_who(
        self,
        lgnum: str,
        rsrc: str,
    ) -> dict[str, Any]:
        """Fetch a new warehouse order for a robot resource. [P1]

        Calls ``GetNewRobotWho`` function import (GET).  Returns the
        next eligible warehouse order assigned by SAP EWM's queue logic.

        Args:
            lgnum: Warehouse number.
            rsrc: Robot resource ID.

        Returns:
            The next WHO dict assigned to this resource.

        Raises:
            NoOrderFoundError: No eligible orders.
            NoRobotResourceTypeError: Resource type not configured.
        """
        url = self._function_import_url(
            "GetNewRobotWho",
            Lgnum=lgnum,
            Rsrc=rsrc,
        )
        return self._request("GET", url)

    # ── P1: set_robot_status ──────────────────────────────────────────

    def set_robot_status(
        self,
        lgnum: str,
        rsrc: str,
        exccode: str,
    ) -> dict[str, Any]:
        """Set the operational status of a robot resource. [P1]

        Calls ``SetRobotStatus`` function import (POST).  Used to report
        errors, idle, charging, or maintenance status changes.

        Args:
            lgnum: Warehouse number.
            rsrc: Robot resource ID.
            exccode: Exception/status code (see ``ExceptionCode`` enum).

        Returns:
            SAP response dict.

        Raises:
            StatusNotSetError: Status could not be set.
            RobotNotFoundError: Robot resource not found.
        """
        url = self._function_import_url(
            "SetRobotStatus",
            Lgnum=lgnum,
            Rsrc=rsrc,
            Exccode=exccode,
        )
        return self._request("POST", url)

    # ── P1: get_in_process_who ────────────────────────────────────────

    def get_in_process_who(
        self,
        lgnum: str,
        rsrcgrp: str | None = None,
        rsrctype: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get warehouse orders currently in process. [P1]

        Calls ``GetInProcessWho`` function import (GET).

        Args:
            lgnum: Warehouse number.
            rsrcgrp: Optional resource group filter.
            rsrctype: Optional resource type filter (see ``RobotType``).

        Returns:
            List of WHO dicts currently in process.

        Raises:
            WhoNotFoundError: No in-process WHOs found.
        """
        url = self._function_import_url(
            "GetInProcessWho",
            Lgnum=lgnum,
            Rsrcgrp=rsrcgrp,
            Rsrctype=rsrctype,
        )
        result = self._request("GET", url)
        # parse_response already handles unwrapping "results" if present
        if result is None:
            return []
        if isinstance(result, list):
            return result
        # result is a dict, check if it's a single item collection
        if "results" in result and isinstance(result["results"], list):
            return result["results"]
        # single dict result
        return [result]

    # ── P1: get_assigned_robot_who ────────────────────────────────────

    def get_assigned_robot_who(
        self,
        lgnum: str,
        rsrc: str,
    ) -> list[dict[str, Any]]:
        """Get warehouse orders assigned to a specific robot. [P1]

        Calls ``GetRobotWho`` function import (GET).

        Args:
            lgnum: Warehouse number.
            rsrc: Robot resource ID.

        Returns:
            List of WHO dicts assigned to this robot.

        Raises:
            RobotNotFoundError: Robot resource not found.
            WhoNotFoundError: No WHOs assigned.
        """
        url = self._function_import_url(
            "GetRobotWho",
            Lgnum=lgnum,
            Rsrc=rsrc,
        )
        result = self._request("GET", url)
        # parse_response already handles unwrapping "results" if present
        if result is None:
            return []
        if isinstance(result, list):
            return result
        # result is a dict, check if it's a single item collection
        if "results" in result and isinstance(result["results"], list):
            return result["results"]
        # single dict result
        return [result]

    # ═══════════════════════════════════════════════════════════════════
    # P2 Stubs — Planned but not yet implemented
    # ═══════════════════════════════════════════════════════════════════

    def get_new_robotgroup_who(self) -> None:
        """Fetch a warehouse order for a robot group (batch reservation). [P2]

        Planned for batch order reservation scenarios where WHOs are
        assigned to a group rather than an individual robot.

        Reference: SAP ZEWM_ROBCO INTEGRATION - IMPLEMENTATION PLAN 20260711 §2.5
        """
        raise NotImplementedError(
            "get_new_robotgroup_who is a P2 stub — "
            "see plan §2.5 for batch reservation design",
        )

    def unset_who_in_process(self) -> None:
        """Revert a warehouse order's in-process status. [P2]

        Used when a robot fails mid-execution and the WHO needs to be
        released back to the queue without confirmation.

        Reference: SAP ZEWM_ROBCO INTEGRATION - IMPLEMENTATION PLAN 20260711 §2.5
        """
        raise NotImplementedError(
            "unset_who_in_process is a P2 stub — "
            "see plan §2.5 for process reversion design",
        )

    def send_conf_error(self) -> None:
        """Send a confirmation error alert to SAP EWM. [P2]

        Called when task confirmation fails after retries, to ensure
        SAP EWM is aware of the persistent failure state.

        Reference: SAP ZEWM_ROBCO INTEGRATION - IMPLEMENTATION PLAN 20260711 §2.5
        """
        raise NotImplementedError(
            "send_conf_error is a P2 stub — "
            "see plan §2.5 for error alert design",
        )

    def move_who_to_error_queue(self) -> None:
        """Move a warehouse order to the SAP EWM error queue. [P2]

        Requires SAP OData function import exposure of the error queue
        operation.  Currently not available in the standard ZEWM_ROBCO_SRV.

        Reference: SAP ZEWM_ROBCO INTEGRATION - IMPLEMENTATION PLAN 20260711 §2.5
        """
        raise NotImplementedError(
            "move_who_to_error_queue is a P2 stub — "
            "requires SAP OData function import exposure; see plan §2.5",
        )

    # ═══════════════════════════════════════════════════════════════════
    # Infrastructure
    # ═══════════════════════════════════════════════════════════════════

    def check_connection(self) -> dict[str, Any]:
        """Verify connectivity to the ZEWM_ROBCO_SRV OData service.

        GET ``$metadata`` and return connection status.

        Returns:
            Dict with ``connected``, ``backend``, ``auth_mode`` keys.
        """
        try:
            with self._get_client() as client:
                url = f"{self._base_url}{self._odata_service}/$metadata"
                headers = self._get_csrf_headers(client)
                resp = client.get(
                    url,
                    headers=headers,
                    auth=self._get_auth_for_request(),
                    timeout=10,
                )
                return {
                    "connected": resp.status_code == 200,
                    "backend": "zewm_robco",
                    "mode": "odata",
                    "auth_mode": self._auth_mode,
                    "warehouse_configured": self._is_configured(),
                    "details": {"status_code": resp.status_code},
                }
        except Exception as exc:
            return {
                "connected": False,
                "backend": "zewm_robco",
                "mode": "odata",
                "auth_mode": self._auth_mode,
                "warehouse_configured": self._is_configured(),
                "error": str(exc)[:200],
            }

    def close(self) -> None:
        """Release Redis and httpx connections.

        Safe to call multiple times.  The ZewmRobcoClient owns the Redis
        connection; ``_ZewmCsrfManager`` and ``OAuth2TokenManager`` share
        it but have been modified to be no-ops for close() to prevent
        double-closing of the Redis connection.
        """
        # Clear references to managers (their close() methods are no-ops)
        self._csrf = None
        self._oauth2 = None

        # Close the Redis connection (owned by this client)
        if self._redis is not None:
            with contextlib.suppress(Exception):
                self._redis.close()
            self._redis = None
        logger.debug("ZewmRobcoClient connections closed")

    # ── Validation ────────────────────────────────────────────────────

    @staticmethod
    def validate_config(config: dict[str, Any]) -> list[str]:
        """Validate client configuration and return a list of errors.

        Args:
            config: Configuration dictionary (same structure as ``__init__``).

        Returns:
            List of error messages.  Empty list means config is valid.
        """
        errors: list[str] = []
        auth_mode = config.get("auth_mode", "basic")

        if auth_mode == "oauth2":
            oauth2_cfg = config.get("oauth2", {})
            if not oauth2_cfg.get("token_url"):
                errors.append("OAuth2 token_url not configured")
            if not oauth2_cfg.get("client_id"):
                errors.append("OAuth2 client_id not configured")
        else:
            if not config.get("user"):
                errors.append("SAP user not configured for basic auth")
            pw_file = config.get("password_file", "")
            password = config.get("password", "")
            if not password and not pw_file:
                errors.append(
                    "Neither password nor password_file configured for basic auth",
                )

        base_url = config.get("base_url", "")
        if not base_url or base_url == DEFAULT_BASE_URL:
            logger.info(
                "base_url may be default (%s) — verify config", DEFAULT_BASE_URL,
            )

        client_val = config.get("client", "")
        if not client_val or client_val == "100":
            logger.info("SAP client may be default (100) — verify tenant")

        return errors

    def _is_configured(self) -> bool:
        """Check if auth is properly configured."""
        if self._auth_mode == "oauth2":
            return bool(self._oauth2_cfg.get("token_url"))
        return self._auth is not None and bool(self._auth[0])
