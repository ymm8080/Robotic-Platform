"""Tests for Redis-backed rate limiting middleware."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from rate_limiter import (
    _READ_LIMIT,
    _WRITE_LIMIT,
    RateLimitMiddleware,
    _client_ip,
    _tier_for,
)

logging.getLogger("rate_limiter").setLevel(logging.CRITICAL)


@pytest.fixture
def redis_mock():
    return MagicMock()


@pytest.fixture
def app(redis_mock):
    application = FastAPI()
    application.add_middleware(RateLimitMiddleware, redis_client=redis_mock)

    @application.get("/ping")
    async def ping():
        return {"ok": True}

    @application.post("/write")
    async def write():
        return {"ok": True}

    @application.get("/health")
    async def health():
        return {"status": "healthy"}

    return application


@pytest.fixture
def client(app):
    return TestClient(app)


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
    def test_exempt_path_skips_redis(self, redis_mock, client):
        """Health endpoint should not touch Redis."""
        resp = client.get("/health")
        assert resp.status_code == 200
        redis_mock.eval.assert_not_called()

    def test_no_redis_fails_open(self):
        """When Redis is None, all requests pass through."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis_client=None)

        @app.get("/ping")
        async def ping():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_under_limit_allowed(self, redis_mock, client):
        redis_mock.eval.return_value = 1
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(_READ_LIMIT)
        assert resp.headers["X-RateLimit-Remaining"] == str(_READ_LIMIT - 1)

    def test_over_limit_returns_429(self, redis_mock, client):
        redis_mock.eval.return_value = _READ_LIMIT + 1
        resp = client.get("/ping")
        assert resp.status_code == 429
        assert resp.json()["error"] == "rate_limit_exceeded"
        assert "Retry-After" in resp.headers

    def test_redis_error_fails_open(self, redis_mock, client):
        redis_mock.eval.side_effect = Exception("connection refused")
        resp = client.get("/ping")
        assert resp.status_code == 200

    def test_eval_called_with_lua_script(self, redis_mock, client):
        redis_mock.eval.return_value = 1
        client.get("/ping")
        redis_mock.eval.assert_called_once()
        script = redis_mock.eval.call_args[0][0]
        assert "INCR" in script
        assert "EXPIRE" in script

    def test_write_endpoint_uses_write_limit(self, redis_mock, client):
        redis_mock.eval.return_value = 1
        resp = client.post("/write")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == str(_WRITE_LIMIT)

    def test_write_over_limit_429(self, redis_mock, client):
        redis_mock.eval.return_value = _WRITE_LIMIT + 1
        resp = client.post("/write")
        assert resp.status_code == 429
        assert resp.headers["X-RateLimit-Limit"] == str(_WRITE_LIMIT)

    def test_eval_return_bytes_is_converted(self, redis_mock, client):
        """Some Redis clients return bytes from eval; ensure it is coerced."""
        redis_mock.eval.return_value = b"5"
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Remaining"] == str(_READ_LIMIT - 5)
