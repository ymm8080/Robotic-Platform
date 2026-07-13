"""Tests for TrafficCoordinatorClient — HTTP client for v5.0 coordinator."""

import json
import logging
from unittest.mock import MagicMock

# Suppress logger noise during tests
logging.getLogger("clients.traffic_coordinator_client").setLevel(logging.CRITICAL)

from clients.traffic_coordinator_client import (
    DEFAULT_COORDINATOR_URL,
    ClientResult,
    TrafficCoordinatorClient,
)


class TestClientResult:
    """Tests for the ClientResult dataclass."""

    def test_ok_result(self):
        r = ClientResult(ok=True, status=200, data={"status": "healthy"})
        assert r.ok
        assert r.status == 200
        assert r.data == {"status": "healthy"}
        assert r.error is None

    def test_error_result(self):
        r = ClientResult(ok=False, status=500, error="timeout")
        assert not r.ok
        assert r.error == "timeout"

    def test_defaults(self):
        r = ClientResult(ok=True)
        assert r.status is None
        assert r.data is None
        assert r.error is None


class TestTrafficCoordinatorClient:
    """Tests for the TrafficCoordinatorClient."""

    def test_default_constructor(self):
        client = TrafficCoordinatorClient()
        assert client.base_url == DEFAULT_COORDINATOR_URL
        assert client.api_key == ""
        assert client.timeout == 10

    def test_custom_base_url(self):
        client = TrafficCoordinatorClient(base_url="http://localhost:9999")
        assert client.base_url == "http://localhost:9999"

    def test_trailing_slash_stripped(self):
        client = TrafficCoordinatorClient(base_url="http://localhost:9999/")
        assert client.base_url == "http://localhost:9999"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("TC_API_KEY", "secret-123")
        client = TrafficCoordinatorClient()
        assert client.api_key == "secret-123"

    def test_api_key_explicit_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("TC_API_KEY", "env-secret")
        client = TrafficCoordinatorClient(api_key="explicit-secret")
        assert client.api_key == "explicit-secret"

    def test_custom_timeout(self):
        client = TrafficCoordinatorClient(timeout=5.0)
        assert client.timeout == 5.0

    # ── HTTP mocking helpers ──────────────────────────────────────

    @staticmethod
    def _mock_urlopen(monkeypatch, status=200, body=None, exc=None):
        """Patch urlopen to return a controlled response or raise."""
        mock = MagicMock()
        if exc:
            mock.side_effect = exc
        else:
            resp = MagicMock()
            resp.status = status
            resp.read.return_value = json.dumps(body or {}).encode()
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            mock.return_value = resp
        monkeypatch.setattr("clients.traffic_coordinator_client.urlopen", mock)
        return mock

    # ── health ───────────────────────────────────────────────────

    def test_health_ok(self, monkeypatch):
        self._mock_urlopen(monkeypatch, body={"status": "healthy", "version": "5.0"})
        client = TrafficCoordinatorClient()
        result = client.health()
        assert result.ok
        assert result.data["status"] == "healthy"

    def test_health_no_auth_header(self, monkeypatch):
        """Health endpoint should NOT send API key."""
        mock = self._mock_urlopen(monkeypatch)
        client = TrafficCoordinatorClient(api_key="secret")
        client.health()
        req = mock.call_args[0][0]
        # urllib lowercases header keys: X-API-Key → X-api-key
        assert req.get_header("X-api-key") is None

    def test_health_http_error(self, monkeypatch):
        from urllib.error import HTTPError

        url = f"{DEFAULT_COORDINATOR_URL}/health"
        resp = MagicMock()
        resp.status = 503
        resp.code = 503
        resp.reason = "Service Unavailable"
        resp.read.return_value = b'{"error": "down"}'
        self._mock_urlopen(monkeypatch, exc=HTTPError(url, 503, "Unavailable", {}, resp))
        client = TrafficCoordinatorClient()
        result = client.health()
        assert not result.ok
        assert result.status == 503

    # ── state ────────────────────────────────────────────────────

    def test_state_sends_auth(self, monkeypatch):
        mock = self._mock_urlopen(monkeypatch, body={"robots": {}})
        client = TrafficCoordinatorClient(api_key="secret")
        client.state()
        req = mock.call_args[0][0]
        # urllib lowercases header keys: X-API-Key → X-api-key
        assert req.get_header("X-api-key") == "secret"

    def test_state_no_auth_if_no_key(self, monkeypatch):
        mock = self._mock_urlopen(monkeypatch, body={"robots": {}})
        client = TrafficCoordinatorClient()
        client.state()
        req = mock.call_args[0][0]
        assert req.get_header("X-api-key") is None

    # ── ingest_state ─────────────────────────────────────────────

    def test_ingest_state_posts_json(self, monkeypatch):
        mock = self._mock_urlopen(monkeypatch, body={"accepted": True})
        client = TrafficCoordinatorClient()
        payload = {"serialNumber": "mir-001", "x": 1.0, "y": 2.0}
        result = client.ingest_state("mir", payload)
        assert result.ok
        req = mock.call_args[0][0]
        assert req.method == "POST"
        sent = json.loads(req.data)
        assert sent["serialNumber"] == "mir-001"

    def test_ingest_state_url_encodes_brand(self, monkeypatch):
        mock = self._mock_urlopen(monkeypatch)
        client = TrafficCoordinatorClient()
        client.ingest_state("MiR", {})
        req = mock.call_args[0][0]
        assert "/ingest/MiR" in req.full_url

    # ── submit_order ─────────────────────────────────────────────

    def test_submit_order(self, monkeypatch):
        mock = self._mock_urlopen(monkeypatch, body={"order_id": "O1", "status": "accepted"})
        client = TrafficCoordinatorClient()
        order = {"order_id": "O1", "origin_lane": "L_A_B", "destination_lane": "L_B_C"}
        result = client.submit_order(order)
        assert result.ok
        req = mock.call_args[0][0]
        assert "/order" in req.full_url

    def test_submit_order_error(self, monkeypatch):
        from urllib.error import HTTPError

        url = f"{DEFAULT_COORDINATOR_URL}/order"
        resp = MagicMock()
        resp.code = 409
        resp.reason = "Conflict"
        resp.read.return_value = b'{"error": "zone locked"}'
        self._mock_urlopen(monkeypatch, exc=HTTPError(url, 409, "Conflict", {}, resp))
        client = TrafficCoordinatorClient()
        result = client.submit_order({"order_id": "O1"})
        assert not result.ok
        assert result.status == 409
        assert "zone locked" in result.error

    # ── cancel_order ─────────────────────────────────────────────

    def test_cancel_order(self, monkeypatch):
        mock = self._mock_urlopen(monkeypatch, body={"cancelled": True})
        client = TrafficCoordinatorClient()
        result = client.cancel_order("O1")
        assert result.ok
        req = mock.call_args[0][0]
        assert "/order/O1/cancel" in req.full_url

    # ── version ──────────────────────────────────────────────────

    def test_version(self, monkeypatch):
        self._mock_urlopen(monkeypatch, body={"versions": ["4.0", "5.0"]})
        client = TrafficCoordinatorClient()
        result = client.version()
        assert result.ok
        assert "5.0" in result.data["versions"]

    # ── metrics ──────────────────────────────────────────────────

    def test_metrics(self, monkeypatch):
        self._mock_urlopen(monkeypatch, body={"uptime": 3600})
        client = TrafficCoordinatorClient()
        result = client.metrics()
        assert result.ok

    # ── error handling ───────────────────────────────────────────

    def test_urlerror_unreachable(self, monkeypatch):
        from urllib.error import URLError

        self._mock_urlopen(monkeypatch, exc=URLError("connection refused"))
        client = TrafficCoordinatorClient()
        result = client.health()
        assert not result.ok
        assert "unreachable" in result.error

    def test_timeout_handled(self, monkeypatch):
        self._mock_urlopen(monkeypatch, exc=TimeoutError("timed out"))
        client = TrafficCoordinatorClient()
        result = client.health()
        assert not result.ok
        assert "timeout" in result.error

    def test_oserror_handled(self, monkeypatch):
        self._mock_urlopen(monkeypatch, exc=OSError("broken pipe"))
        client = TrafficCoordinatorClient()
        result = client.health()
        assert not result.ok
        assert "broken pipe" in result.error
