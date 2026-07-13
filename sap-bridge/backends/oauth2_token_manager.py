"""OAuth2 token manager for SAP S/4HANA integration.

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
      client_id: "${SAP_OAUTH_CLIENT_ID:-}"
      client_secret_file: "${SAP_OAUTH_CLIENT_SECRET_FILE:-/run/secrets/sap_oauth_client_secret}"
      scope: ""  # optional; S/4HANA usually does not require scope

Credentials follow iron rule #5 — Docker Secrets only.
"""

from __future__ import annotations

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
        with open(secret_file) as f:
            secret = f.read().strip()
            if not secret:
                raise ValueError(f"OAuth2 client secret file is empty: {secret_file}")
            return secret
    except FileNotFoundError:
        logger.error("OAuth2 client secret file not found at configured path")
        raise


class OAuth2TokenManager:
    """Manages OAuth2 bearer tokens for SAP S/4HANA with Redis caching.

    Uses client_credentials grant (RFC 6749 §4.4) — no user interaction.
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
        """Return cached token if still valid, None otherwise."""
        token = self._redis.get(self._cache_key)
        if token:
            logger.debug("OAuth2 token served from cache")
            return token
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

        body = resp.json()
        access_token = body.get("access_token")
        if not access_token:
            raise RuntimeError("OAuth2 token response missing access_token")

        expires_in = int(body.get("expires_in", _DEFAULT_TOKEN_TTL_S))
        # Cache with safety margin to avoid using an expired token
        cache_ttl = max(expires_in - _TOKEN_SAFETY_MARGIN_S, 60)

        self._redis.setex(self._cache_key, cache_ttl, access_token)
        self._redis.set("sap:oauth2:last_refresh", str(time.time()))

        token_type = body.get("token_type", "Bearer")
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
        return self.fetch_new(client)

    def invalidate(self) -> None:
        """Force token invalidation (e.g., after a 401 response)."""
        self._redis.delete(self._cache_key)
        logger.info("OAuth2 token invalidated — will refresh on next request")

    def close(self) -> None:
        """Close Redis connection.

        No-op: Redis connection is owned by the caller.
        """
        logger.debug("OAuth2TokenManager.close() is a no-op")
