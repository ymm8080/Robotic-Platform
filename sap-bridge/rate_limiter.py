"""Redis-backed rate limiting middleware for FastAPI.

Sliding window counter per client IP with separate tiers for read vs write.

Tiers (per AGENTS.md rate limits):
  GET  → 100/min  (read endpoints)
  POST → 30/min   (write endpoints)

Exempt paths: /health, /ready, /live, /metrics
"""
from __future__ import annotations

import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────
_READ_LIMIT = int(os.getenv("RATE_LIMIT_READ_PER_MIN", "100"))
_WRITE_LIMIT = int(os.getenv("RATE_LIMIT_WRITE_PER_MIN", "30"))
_WINDOW_SECONDS = 60

_EXEMPT_PATHS = frozenset({"/health", "/ready", "/live", "/metrics"})

# Redis key prefix
_REDIS_PREFIX = "ratelimit"

# Atomic INCR + EXPIRE Lua script (fixes race between INCR and EXPIRE)
_INCR_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('INCR', key)
if current == 1 then
    redis.call('EXPIRE', key, window)
end
return current
"""


def _client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For from reverse proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _tier_for(method: str) -> int:
    """Return rate limit for the HTTP method."""
    return _WRITE_LIMIT if method in ("POST", "PUT", "PATCH", "DELETE") else _READ_LIMIT


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter backed by Redis.

    Falls back to allow-all if Redis is unavailable (fail-open).
    """

    def __init__(self, app, redis_client=None) -> None:
        super().__init__(app)
        self._redis = redis_client

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip exempt paths
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        # Skip if no Redis configured (fail-open for tests / dev)
        if self._redis is None:
            return await call_next(request)

        ip = _client_ip(request)
        limit = _tier_for(request.method)
        window_key = f"{_REDIS_PREFIX}:{ip}:{request.method}:{int(time.time()) // _WINDOW_SECONDS}"

        try:
            count = int(
                self._redis.eval(_INCR_SCRIPT, 1, window_key, limit, _WINDOW_SECONDS)
            )
        except Exception as exc:
            logger.warning("rate limiter Redis error (fail-open): %s", exc)
            return await call_next(request)

        if count > limit:
            retry_after = _WINDOW_SECONDS - (int(time.time()) % _WINDOW_SECONDS)
            logger.warning(
                "rate limit exceeded: ip=%s method=%s path=%s count=%d/%d",
                ip, request.method, path, count, limit,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": f"Limit: {limit} requests per {_WINDOW_SECONDS}s",
                    "retryAfter": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        # Add rate limit headers for client visibility
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response
