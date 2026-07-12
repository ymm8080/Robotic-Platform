"""Shared OAuth2 token manager for SAP integrations (EWM Backend + ZEWM ROBCO Client).

S/4HANA (on-premise 2023+ and Cloud Private Edition) recommends OAuth2
client_credentials grant for machine-to-machine integration.  This module
fetches, caches, and refreshes bearer tokens via Redis.

Token flow:
  1. POST to token_url with client_id + client_secret (form-urlencoded)
  2. Receive {access_token, expires_in, token_type}
  3. Cache in Redis with TTL = expires_in - 60s safety margin
  4. On expiry or 401 response → fetch new token

Config (config.yaml per-warehouse):
    auth_mode: oauth2
    oauth2:
      token_url: "https://sap-s4hana:44300/sap/bc/sec/oauth2/token"
<<<<<<< HEAD
      client_id: "${SAP_OAUTH_CLIENT_ID:-}"
      client_secret_file: "${SAP_OAUTH_CLIENT_SECRET_FILE:-/run/secrets/sap_oauth_client_secret}"
      scope: ""  # optional; S/4HANA usually does not require scope

Credentials follow iron rule #5 — Docker Secrets only.
=======
      client_id: "<from env SAP_OAUTH_CLIENT_ID>"
      client_secret_file: "/run/secrets/sap_oauth_client_secret"
      scope: ""  # optional; S/4HANA usually does not require scope

Credentials follow iron rule #5 — Docker Secrets only.
The Redis client passed to OAuth2TokenManager should use
``decode_responses=True`` so that ``get_token`` returns ``str``.
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
"""

from __future__ import annotations

<<<<<<< HEAD
=======
import contextlib
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
import logging
import time

import httpx
import redis as rd

logger = logging.getLogger(__name__)

# Redis cache keys (namespaced per token_url to support multiple SAP systems)
_TOKEN_KEY_PREFIX = "sap:oauth2:token"
# Safety margin: refresh token 60s before actual expiry
_TOKEN_SAFETY_MARGIN_S = 60
# Default token TTL if SAP doesn't return expires_in
_DEFAULT_TOKEN_TTL_S = 3600


def read_client_secret(secret_file: str) -> str:
    """Read OAuth2 client secret from Docker secret file."""
    try:
<<<<<<< HEAD
        with open(secret_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error(f"OAuth2 client secret file not found: {secret_file}")
=======
        with open(secret_file, encoding="utf-8") as f:
            secret = f.read().strip()
            if not secret:
                raise ValueError(f"OAuth2 client secret file is empty: {secret_file}")
            return secret
    except FileNotFoundError:
        logger.error("OAuth2 client secret file not found at configured path")
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
        raise


class OAuth2TokenManager:
    """Manages OAuth2 bearer tokens for SAP S/4HANA with Redis caching.

<<<<<<< HEAD
    Uses client_credentials grant (RFC 6749 § 4.4) — no user interaction.
=======
    Uses client_credentials grant (RFC 6749 §4.4) — no user interaction.
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
    Thread-safe: Redis GET/SET are atomic for single keys.
    """

    def __init__(
        self,
        redis_client: rd.Redis,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "",
    ) -> None:
        self._redis = redis_client
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._cache_key = f"{_TOKEN_KEY_PREFIX}:{token_url}"

    def get_token(self) -> str | None:
<<<<<<< HEAD
        """Return cached token if still valid, None otherwise."""
        token = self._redis.get(self._cache_key)
        if token:
            logger.debug("OAuth2 token served from cache")
            return token.decode() if isinstance(token, bytes) else token
=======
        """Return cached token if still valid, None otherwise.

        The Redis client should be configured with ``decode_responses=True``
        so that ``GET`` returns ``str``.  If it returns ``bytes``, we decode
        here as a safety net.
        """
        token = self._redis.get(self._cache_key)
        if token:
            if isinstance(token, bytes):
                token = token.decode("utf-8")
            logger.debug("OAuth2 token served from cache")
            return token
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
        return None

    def fetch_new(self, client: httpx.Client) -> str:
        """Fetch a new bearer token via client_credentials grant.

        Raises:
            RuntimeError: if SAP returns an error or no access_token.
        """
        data = {"grant_type": "client_credentials"}
        if self._scope:
            data["scope"] = self._scope

        resp = client.post(
            self._token_url,
            data=data,
            auth=(self._client_id, self._client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if resp.status_code != 200:
            logger.error(
                f"OAuth2 token request failed: {resp.status_code} {resp.text[:200]}"
            )
            raise RuntimeError(
                f"OAuth2 token endpoint returned {resp.status_code}"
            )

<<<<<<< HEAD
        try:
            body = resp.json()
        except ValueError:
            logger.error(
                f"OAuth2 token response is not valid JSON: {resp.text[:200]}"
            )
            raise RuntimeError("OAuth2 token endpoint returned non-JSON response")

=======
        body = resp.json()
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
        access_token = body.get("access_token")
        if not access_token:
            raise RuntimeError("OAuth2 token response missing access_token")

<<<<<<< HEAD
        expires_in = int(body.get("expires_in") or _DEFAULT_TOKEN_TTL_S)
=======
        expires_in = int(body.get("expires_in", _DEFAULT_TOKEN_TTL_S))
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
        # Cache with safety margin to avoid using an expired token
        cache_ttl = max(expires_in - _TOKEN_SAFETY_MARGIN_S, 60)

        self._redis.setex(self._cache_key, cache_ttl, access_token)
        self._redis.set("sap:oauth2:last_refresh", str(time.time()))

        token_type = body.get("token_type", "Bearer")
<<<<<<< HEAD
        if token_type.lower() != "bearer":
            logger.warning("Unexpected OAuth2 token_type: %s", token_type)
=======
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
        logger.info(
            f"Fetched new OAuth2 token (expires_in={expires_in}s, "
            f"cached_ttl={cache_ttl}s, type={token_type})"
        )
        return access_token

    def get_valid_token(self, client: httpx.Client) -> str:
        """Return a valid token — from cache or fetch new.

        This is the main entry point for callers.
        """
        token = self.get_token()
        if token:
            return token
<<<<<<< HEAD
        try:
            return self.fetch_new(client)
        except RuntimeError:
            logger.error("Failed to fetch new OAuth2 token")
            raise

    def invalidate(self) -> None:
        """Force token invalidation (e.g., after a 401 response)."""
        try:
            self._redis.delete(self._cache_key)
            logger.info("OAuth2 token invalidated — will refresh on next request")
        except Exception:
            logger.warning("Failed to invalidate OAuth2 token in Redis")

    def close(self) -> None:
        """Close Redis connection.

        No-op: Redis connection is owned by the caller.
        """
        logger.debug("OAuth2TokenManager.close() is a no-op")
# EOF
=======
        return self.fetch_new(client)

    def invalidate(self) -> None:
        """Force token invalidation (e.g., after a 401 response)."""
        self._redis.delete(self._cache_key)
        logger.info("OAuth2 token invalidated — will refresh on next request")

    def close(self) -> None:
        """Close Redis connection."""
        with contextlib.suppress(Exception):
            self._redis.close()
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
