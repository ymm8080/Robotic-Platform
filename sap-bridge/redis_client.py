"""Shared Redis connection helper with TLS detection."""

import os

import redis


def redis_from_url(url: str, **kwargs) -> redis.Redis:
    """Create a Redis client honoring rediss:// and REDIS_SSL settings."""
    use_ssl = url.startswith("rediss://") or os.getenv("REDIS_SSL", "false").lower() == "true"
    if use_ssl:
        kwargs.setdefault("ssl", True)
        kwargs.setdefault("ssl_cert_reqs", os.getenv("REDIS_SSL_CERT_REQS", "required"))
    return redis.from_url(url, **kwargs)


def async_redis_from_url(url: str, **kwargs):
    """Create an async Redis client honoring rediss:// and REDIS_SSL settings."""
    import redis.asyncio as aioredis

    use_ssl = url.startswith("rediss://") or os.getenv("REDIS_SSL", "false").lower() == "true"
    if use_ssl:
        kwargs.setdefault("ssl", True)
        kwargs.setdefault("ssl_cert_reqs", os.getenv("REDIS_SSL_CERT_REQS", "required"))
    return aioredis.from_url(url, **kwargs)
