"""Tests for Redis-backed rate limiting middleware."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

logging.getLogger("rate_limiter").setLevel(logging.CRITICAL)

from rate_limiter import (
    RateLimitMiddleware,
    _client_ip,
    _tier_for,
    _READ_LIMIT,
    _WRITE_LIMIT,
)


def _make_app(redis_mock=None):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, redis_client=redis_mock)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.post("/write")
    async def write():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


class TestTierFor:
    def test_get_is_read_limit(self):
        assert _tier_for("GET") == _READ_LIMIT

    def test_post_is_write_limit(self):
        assert _tier_for("POST") == _WRITE_LIMIT

    def test_put_is_write_limit(self):
        assert _tier_for("PUT") == _WRITE_LIMIT

    def test_delete_is_write_limit(self):
        assert _tier_for("DELETE") == _WRITE_LIMIT


class TestClientIp:
    def test_direct_ip(self):
        req = MagicMock()
        req.headers = {}
        req.client = MagicMock()
        req.client.host = "192.168.1.1"
        assert _client_ip(req) == "192.168.1.1"

    def test_forwarded_for(self):
        req = MagicMock()
        req.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2"}
        req.client = MagicMock()
        req.client.host = "192.168.1.1"
        assert _client_ip(req) == "10.0.0.1"


class TestRateLimitMiddleware:
    def test_exempt_path_skips_redis(self):
        """Health endpoint should not touch Redis."""
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 1
        app = _make_app(redis_mock)
        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 200
        redis_mock.incr.assert_not_called()

    def test_no_redis_fails_open(self):
        """When Redis is None, all requests pass through."""
        app = _make_app(redis_mock=None)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_under_limit_allowed(self):
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 1
        app = _make_app(redis_mock)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(_READ_LIMIT)
        assert resp.headers["X-RateLimit-Remaining"] == str(_READ_LIMIT - 1)

    def test_over_limit_returns_429(self):
        redis_mock = MagicMock()
        redis_mock.incr.return_value = _READ_LIMIT + 1
        app = _make_app(redis_mock)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 429
        assert resp.json()["error"] == "rate_limit_exceeded"
        assert "Retry-After" in resp.headers

    def test_redis_error_fails_open(self):
        redis_mock = MagicMock()
        redis_mock.incr.side_effect = Exception("connection refused")
        app = _make_app(redis_mock)
        client = TestClient(app)

        resp = client.get("/ping")
        assert resp.status_code == 200

    def test_expire_called_on_first_request(self):
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 1
        app = _make_app(redis_mock)
        client = TestClient(app)

        client.get("/ping")
        redis_mock.expire.assert_called_once()

    def test_expire_not_called_on_subsequent(self):
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 5
        app = _make_app(redis_mock)
        client = TestClient(app)

        client.get("/ping")
        redis_mock.expire.assert_not_called()

    def test_write_endpoint_uses_write_limit(self):
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 1
        app = _make_app(redis_mock)
        client = TestClient(app)

        resp = client.post("/write")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(_WRITE_LIMIT)

    def test_write_over_limit_429(self):
        redis_mock = MagicMock()
        redis_mock.incr.return_value = _WRITE_LIMIT + 1
        app = _make_app(redis_mock)
        client = TestClient(app)

        resp = client.post("/write")
        assert resp.status_code == 429
        assert resp.headers["X-RateLimit-Limit"] == str(_WRITE_LIMIT)
