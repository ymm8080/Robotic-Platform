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
import logging
import os
import time
from collections.abc import Callable
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
CSRF_REDIS_KEY = "sap:zewm_robco:csrf_token"
CSRF_REDIS_COOKIE_KEY = "sap:zewm_robco:csrf_cookies"
CSRF_REDIS_REFRESH_KEY = "sap:zewm_robco:csrf_last_refresh"
CONFIRM_RETRY_MAX = 5
CONFIRM_RETRY_BACKOFF_BASE = 1.0
CONFIRM_RETRY_BACKOFF_CAP = 30.0


def _read_password(password_file: str) -> str:
    """Read password from a Docker secret file."""
    try:
        with open(password_file) as f:
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
        auth_headers_fn: Callable[[httpx.Client], dict[str, str]] | None = None,
    ):
        self._redis = redis_client
        self._auth = auth
        self._auth_headers_fn = auth_headers_fn or (lambda _client: {})

    def get_token(self) -> tuple[str, str] | None:
        """Return cached (token, cookies) or None."""
        token = self._redis.get(CSRF_REDIS_KEY)
        cookies = self._redis.get(CSRF_REDIS_COOKIE_KEY)
        if token and cookies:
            return (token, cookies)
        return None

    def set_token(self, token: str, cookies: str) -> None:
        """Cache CSRF token and cookies in Redis."""
        pipe = self._redis.pipeline()
        pipe.setex(CSRF_REDIS_KEY, CSRF_REFRESH_INTERVAL, token)
        pipe.setex(CSRF_REDIS_COOKIE_KEY, CSRF_REFRESH_INTERVAL, cookies)
        pipe.set(CSRF_REDIS_REFRESH_KEY, str(time.time()))
        pipe.execute()

    def fetch_new(
        self,
        client: httpx.Client,
        base_url: str,
        odata_service: str,
    ) -> tuple[str, str]:
        """Fetch a fresh CSRF token from SAP via $metadata."""
        url = f"{base_url}{odata_service}/$metadata"
        headers = {"X-CSRF-Token": "Fetch", **self._auth_headers_fn(client)}
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

    def close(self) -> None:
        """No-op — Redis connection is owned by the caller."""
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
            self._cfg.get("confirm_retry_max", CONFIRM_RETRY_MAX),
        )
        self._confirm_retry_backoff_base = float(
            self._cfg.get("confirm_retry_backoff_base", CONFIRM_RETRY_BACKOFF_BASE),
        )
        self._confirm_retry_backoff_cap = float(
            self._cfg.get("confirm_retry_backoff_cap", CONFIRM_RETRY_BACKOFF_CAP),
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

        Auth headers are fetched lazily via a callable to avoid creating
        an unnecessary HTTP connection during initialization.
        """
        if self._csrf is None:
            self._csrf = _ZewmCsrfManager(
                self._ensure_redis(),
                auth=self._auth,
                auth_headers_fn=self._get_auth_headers,
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
        """Token-bucket rate limiter (simple sleep-based)."""
        if not self._enabled:
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

    def _get_headers(
        self,
        csrf_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> dict[str, str]:
        """Build standard HTTP headers for ZEWM_ROBCO_SRV requests."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-sap-client": self._client,
        }
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        if client and self._auth_mode == "oauth2":
            headers.update(self._get_auth_headers(client))
        return headers

    def _get_csrf_headers(self, client: httpx.Client) -> dict[str, str]:
        """Get headers including a valid CSRF token.

        Uses cached token if available, otherwise fetches a new one.
        """
        csrf = self._ensure_csrf()
        cached = csrf.get_token()
        if cached:
            token, cookies = cached
            return {**self._get_headers(token, client), "Cookie": cookies}
        token, cookies = csrf.fetch_new(client, self._base_url, self._odata_service)
        return {**self._get_headers(token, client), "Cookie": cookies}

    # ── OData URL construction ────────────────────────────────────────

    def _function_import_url(self, name: str, **params: Any) -> str:
        """Build a full OData function-import URL with query parameters.

        SAP ZEWM_ROBCO_SRV uses positional query-string parameters wrapped in
        single quotes.

        Example::

            _function_import_url(
                "AssignRobotWho",
                Lgnum="WH01", Rsrc="MIR_001", Who="123",
            )
            # → ".../AssignRobotWho?Lgnum='WH01'&Rsrc='MIR_001'&Who='123'"

        Args:
            name: Function import name (e.g. ``"AssignRobotWho"``).
            **params: Query parameters as keyword arguments.

        Returns:
            Full URL string.
        """
        base = f"{self._base_url}{self._odata_service}/{name}"
        if not params:
            return base
        parts: list[str] = []
        for k, v in params.items():
            if v is not None:
                escaped = str(v).replace("'", "''")
                parts.append(f"{k}='{escaped}'")
        if not parts:
            return base
        return f"{base}?{'&'.join(parts)}"

    # ── Response parsing ──────────────────────────────────────────────

    @staticmethod
    def _parse_response(resp: httpx.Response) -> dict[str, Any]:
        """Unwrap SAP OData V2 ``{"d": {...}}`` envelope.

        SAP NetWeaver Gateway wraps entity responses in a ``d`` key.
        Collection responses may use ``d.results``.  This method handles
        both, returning the unwrapped dict.

        Args:
            resp: The httpx response object.

        Returns:
            The unwrapped response body dict.
        """
        body = resp.json()
        if not isinstance(body, dict):
            return body
        return body.get("d", body)

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
            err = body.get("error", {})
            raw_code = err.get("code", "INTERNAL_ERROR")
            # Strip SAP's "/NNN" numeric suffix
            error_code = raw_code.split("/")[0]
            detail = err.get("message", {}).get("value", "")
            raise_for_error_code(error_code, detail)
        except (ValueError, KeyError, AttributeError) as exc:
            logger.debug("Failed to parse SAP error response: %s", exc)
            raise RobcoInternalError(
                f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

    # ── Core request method ───────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with CSRF retry and error handling.

        This is the central request dispatcher.  On CSRF expiry (403),
        it fetches a fresh token and retries exactly once.  SAP error
        responses are parsed via ``_handle_error_response()``.

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

        with self._get_client() as client:
            headers = self._get_csrf_headers(client)
            full_url = (
                f"{self._base_url}{path}"
                if not path.startswith("http")
                else path
            )

            resp = client.request(
                method=method,
                url=full_url,
                json=body,
                headers=headers,
                auth=self._get_auth_for_request(),
            )

            # CSRF token expired — refresh and retry once
            if resp.status_code == 403:
                logger.info("CSRF token expired, refreshing...")
                csrf = self._ensure_csrf()
                token, cookies = csrf.fetch_new(
                    client, self._base_url, self._odata_service,
                )
                headers["X-CSRF-Token"] = token
                headers["Cookie"] = cookies
                resp = client.request(
                    method=method,
                    url=full_url,
                    json=body,
                    headers=headers,
                    auth=self._get_auth_for_request(),
                )

            # OAuth2 token expired — invalidate and retry once
            if resp.status_code == 401 and self._auth_mode == "oauth2":
                logger.info("OAuth2 token may be expired, invalidating...")
                self._ensure_oauth2().invalidate()
                # Rebuild headers with fresh token
                headers = self._get_csrf_headers(client)
                resp = client.request(
                    method=method,
                    url=full_url,
                    json=body,
                    headers=headers,
                    auth=self._get_auth_for_request(),
                )
                if resp.status_code == 401:
                    logger.error("OAuth2 token refresh failed - still receiving 401")

            # Rate-limited — backoff and retry once
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2))
                delay = min(retry_after, 30)
                logger.warning("SAP rate limited — backing off %ds", delay)
                time.sleep(delay)
                headers = self._get_csrf_headers(client)
                resp = client.request(
                    method=method,
                    url=full_url,
                    json=body,
                    headers=headers,
                    auth=self._get_auth_for_request(),
                )

            # Success paths
            if resp.status_code in (200, 201, 204):
                if resp.status_code == 204 or not resp.text.strip():
                    return {}
                return self._parse_response(resp)

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
        # SAP may return a single object or a list under "results"
        raw = result.get("results", result)
        if isinstance(raw, dict):
            return [raw]
        if isinstance(raw, list):
            return raw
        return []

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
        raw = result.get("results", result)
        if isinstance(raw, dict):
            return [raw]
        if isinstance(raw, list):
            return raw
        return []

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
                headers = self._get_headers(client=client)
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

        Safe to call multiple times.

        Note: _csrf.close() is a no-op and _oauth2.close() would close
        the shared Redis connection, so we close Redis once here.
        """
        self._csrf = None
        if self._oauth2 is not None:
            with contextlib.suppress(Exception):
                self._oauth2.close()
            self._oauth2 = None
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
        if not base_url:
            errors.append("base_url is not configured")
        elif base_url == DEFAULT_BASE_URL:
            logger.info(
                "base_url may be default (%s) — verify config", DEFAULT_BASE_URL,
            )

        client_val = config.get("client", "")
        if not client_val:
            errors.append("SAP client is not configured")
        elif client_val == "100":
            logger.info("SAP client may be default (100) — verify tenant")

        return errors

    def _is_configured(self) -> bool:
        """Check if auth is properly configured."""
        if self._auth_mode == "oauth2":
            return bool(self._oauth2_cfg.get("token_url"))
        return self._auth is not None and bool(self._auth[0])
