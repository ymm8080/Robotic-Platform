"""E2E tests for v4.1 strategy-pattern dispatch.

Tests cover:
  1. StrategyRegistry.get_or_raise() — strict brand lookup (501 on unknown)
  2. StrategyRegistry.verify_version() — VDA5050 version compatibility
  3. Each brand's dispatch() — protocol payload correctness
  4. /api/v1/dispatch HTTP endpoint — full dispatch flow with mocked MQTT
  5. Edge cases: MQTT down, unknown brand, dual-protocol routing

Requires: pytest, pytest-asyncio, httpx
"""

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("MQTT_BROKER", "localhost")


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Schema is initialized by conftest.py session fixture."""
    yield


# ═══════════════════════════════════════════════════════════════════════════
# Part 1: Registry get_or_raise() + verify_version()
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistryGetOrRaise:
    """v4.1: get_or_raise() strict lookup."""

    @pytest.fixture
    def registry(self):
        from strategies.registry import StrategyRegistry

        return StrategyRegistry()

    def test_get_or_raise_known_brand(self, registry):
        """Known brand returns strategy."""
        from strategies.kuka import KukaStrategy

        strategy = registry.get_or_raise("KUKA")
        assert isinstance(strategy, KukaStrategy)
        assert strategy.brand == "KUKA"

    def test_get_or_raise_case_insensitive(self, registry):
        """Case-insensitive lookup."""
        strategy = registry.get_or_raise("kuka")
        assert strategy.brand == "KUKA"

        strategy = registry.get_or_raise("MiR")
        assert strategy.brand == "MiR"

    def test_get_or_raise_unknown_raises(self, registry):
        """Unknown brand raises UnknownBrandError."""
        from strategies.registry import UnknownBrandError

        with pytest.raises(UnknownBrandError) as exc_info:
            registry.get_or_raise("NONEXISTENT")
        assert exc_info.value.brand == "NONEXISTENT"
        assert "KUKA" in exc_info.value.available
        assert "MIR" in exc_info.value.available

    def test_get_or_raise_error_message_contains_available(self, registry):
        """Error message lists available brands."""
        from strategies.registry import UnknownBrandError

        with pytest.raises(UnknownBrandError, match="Available"):
            registry.get_or_raise("FAKE_BRAND")

    def test_get_or_raise_all_six_brands(self, registry):
        """All 6 registered brands resolve without error."""
        for brand in ["KUKA", "MIR", "OTTO", "GEEKPLUS", "HAIROBOTICS", "QUICKTRON"]:
            strategy = registry.get_or_raise(brand)
            assert strategy is not None


class TestRegistryVerifyVersion:
    """v4.1: verify_version() compatibility check."""

    @pytest.fixture
    def registry(self):
        from strategies.registry import StrategyRegistry

        return StrategyRegistry()

    def test_verify_version_kuka_passes(self, registry):
        """KUKA supports v2.0.0 — passes >= 1.1.0."""
        assert registry.verify_version("KUKA") is True

    def test_verify_version_mir_passes(self, registry):
        """MiR supports v1.1.0 — passes >= 1.1.0."""
        assert registry.verify_version("MIR") is True

    def test_verify_version_geekplus_passes(self, registry):
        """Geek+ supports both v1.1.0 and v2.0.0 — passes."""
        assert registry.verify_version("GEEKPLUS") is True

    def test_verify_version_unknown_raises(self, registry):
        """Unknown brand raises UnknownBrandError, not returns False."""
        from strategies.registry import UnknownBrandError

        with pytest.raises(UnknownBrandError):
            registry.verify_version("FAKE")

    def test_verify_version_higher_requirement(self, registry):
        """If we require v3.0.0, all current brands should fail."""
        assert registry.verify_version("KUKA", min_version="3.0.0") is False
        assert registry.verify_version("MIR", min_version="3.0.0") is False


# ═══════════════════════════════════════════════════════════════════════════
# Part 2: Brand dispatch() payload correctness
# ═══════════════════════════════════════════════════════════════════════════


class TestBrandDispatchPayloads:
    """Each brand's dispatch() builds the correct protocol payload."""

    @pytest.fixture
    def base_order(self):
        return {
            "orderId": "TEST-ORD-001",
            "orderUpdateId": 0,
            "nodes": [{"nodeId": "N1", "sequenceId": 1}],
            "edges": [{"edgeId": "E1", "sequenceId": 1}],
            "serialNumber": "ROBOT-001",
        }

    def test_kuka_dispatch_vda5050(self, base_order):
        """KUKA dispatches VDA5050 v2.0 payload."""
        from strategies.kuka import KukaStrategy

        result = KukaStrategy().dispatch(base_order)
        assert result.success is True
        assert result.protocol == "vda5050"
        assert result.payload["orderId"] == "TEST-ORD-001"
        assert result.payload["nodes"] == base_order["nodes"]
        assert result.payload["edges"] == base_order["edges"]

    def test_mir_dispatch_vda5050_v1(self, base_order):
        """MiR dispatches VDA5050 v1.1 payload (simpler, no headerId)."""
        from strategies.mir import MirStrategy

        result = MirStrategy().dispatch(base_order)
        assert result.success is True
        assert result.protocol == "vda5050"
        assert result.payload["orderId"] == "TEST-ORD-001"
        # MiR v1.1 nodes should not have headerId
        assert result.payload["nodes"] == base_order["nodes"]

    def test_otto_dispatch_vda5050(self, base_order):
        """OTTO dispatches VDA5050 v2.0 payload."""
        from strategies.otto import OttoStrategy

        result = OttoStrategy().dispatch(base_order)
        assert result.success is True
        assert result.protocol == "vda5050"
        assert result.payload["orderId"] == "TEST-ORD-001"

    def test_geekplus_dispatch_vda5050_for_m_series(self, base_order):
        """Geek+ M-series → VDA5050 payload."""
        from strategies.geekplus import GeekPlusStrategy

        order = {**base_order, "robotModel": "M1000"}
        result = GeekPlusStrategy().dispatch(order)
        assert result.success is True
        assert result.protocol == "vda5050"
        assert result.payload["orderId"] == "TEST-ORD-001"

    def test_geekplus_dispatch_iop_for_p_series(self, base_order):
        """Geek+ P-series → IOP REST mission payload."""
        from strategies.geekplus import GeekPlusStrategy

        order = {**base_order, "robotModel": "P800", "target": "STATION-A", "source": "STATION-B"}
        result = GeekPlusStrategy().dispatch(order)
        assert result.success is True
        assert result.protocol == "iop"
        assert result.payload["missionId"] == "TEST-ORD-001"
        assert result.payload["robotId"] == "ROBOT-001"
        assert result.payload["target"] == "STATION-A"

    def test_hairobotics_dispatch_vda5050_for_haiport(self, base_order):
        """Hai Robotics HaiPort → VDA5050 payload."""
        from strategies.hairobotics import HaiRoboticsStrategy

        order = {**base_order, "robotType": "HaiPort"}
        result = HaiRoboticsStrategy().dispatch(order)
        assert result.success is True
        assert result.protocol == "vda5050"
        assert result.payload["orderId"] == "TEST-ORD-001"

    def test_hairobotics_dispatch_haiq_for_acr(self, base_order):
        """Hai Robotics ACR → HAIQ-ESS REST payload."""
        from strategies.hairobotics import HaiRoboticsStrategy

        order = {**base_order, "robotType": "ACR", "toteId": "TOTE-001", "source": "A-01-02", "target": "A-03-04"}
        result = HaiRoboticsStrategy().dispatch(order)
        assert result.success is True
        assert result.protocol == "haiq"
        assert result.payload["requestId"] == "TEST-ORD-001"
        assert result.payload["toteId"] == "TOTE-001"
        assert result.payload["sourceLocation"] == "A-01-02"

    def test_quicktron_dispatch_vda5050(self, base_order):
        """Quicktron default → VDA5050 payload."""
        from strategies.quicktron import QuicktronStrategy

        result = QuicktronStrategy().dispatch(base_order)
        assert result.success is True
        assert result.protocol == "vda5050"
        assert result.payload["orderId"] == "TEST-ORD-001"

    def test_quicktron_dispatch_proprietary(self, base_order):
        """Quicktron proprietary → REST mission payload."""
        from strategies.quicktron import QuicktronStrategy

        order = {**base_order, "protocol": "proprietary", "target": "STATION-X"}
        result = QuicktronStrategy().dispatch(order)
        assert result.success is True
        assert result.protocol == "rest"
        assert result.payload["missionId"] == "TEST-ORD-001"
        assert result.payload["station"] == "STATION-X"

    def test_all_brands_dispatch_success(self, base_order):
        """All 6 brands return success=True for a valid order."""
        from strategies import get_registry

        registry = get_registry()
        for brand in registry.list_brands():
            strategy = registry.get(brand)
            result = strategy.dispatch(base_order)
            assert result.success is True, f"{brand} dispatch failed: {result.error}"
            assert result.payload is not None, f"{brand} returned None payload"
            assert result.order_id == "TEST-ORD-001"


# ═══════════════════════════════════════════════════════════════════════════
# Part 3: /api/v1/dispatch HTTP endpoint E2E
# ═══════════════════════════════════════════════════════════════════════════


class TestDispatchEndpointE2E:
    """Full HTTP dispatch flow with mocked MQTT + Redis."""

    @pytest.fixture
    def client(self, setup_db):
        """FastAPI TestClient with mocked MQTT publisher + Redis."""
        from fastapi.testclient import TestClient

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.hgetall.return_value = {}
        mock_redis.keys.return_value = []
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True

        mock_pub = MagicMock()
        mock_pub.is_connected = True
        mock_pub.publish.return_value = 42

        with patch("redis.from_url", return_value=mock_redis), patch("main.get_publisher", return_value=mock_pub):
            from main import app

            with TestClient(app) as c:
                yield c

    def test_dispatch_kuka_success(self, client):
        """Dispatch to KUKA returns 200 with VDA5050 payload."""
        resp = client.post(
            "/api/v1/dispatch",
            json={
                "brand": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "DISPATCH-001",
                "nodes": [{"nodeId": "N1", "sequenceId": 1}],
                "edges": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dispatched"
        assert data["orderId"] == "DISPATCH-001"
        assert data["brand"] == "KUKA"
        assert data["protocol"] == "vda5050"
        assert data["mqttMid"] == 42
        assert data["payload"]["orderId"] == "DISPATCH-001"

    def test_dispatch_mir_success(self, client):
        """Dispatch to MiR returns 200 with VDA5050 payload."""
        resp = client.post(
            "/api/v1/dispatch",
            json={
                "brand": "MiR",
                "serialNumber": "MIR-250",
                "orderId": "DISPATCH-MIR-001",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["protocol"] == "vda5050"

    def test_dispatch_geekplus_iop(self, client):
        """Dispatch to Geek+ P-series returns IOP protocol."""
        resp = client.post(
            "/api/v1/dispatch",
            json={
                "brand": "GeekPlus",
                "serialNumber": "P800-001",
                "orderId": "DISPATCH-IOP-001",
                "robotModel": "P800",
                "target": "STATION-A",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol"] == "iop"
        assert data["payload"]["missionId"] == "DISPATCH-IOP-001"

    def test_dispatch_hairobotics_haiq(self, client):
        """Dispatch to HaiRobotics ACR returns HAIQ protocol."""
        resp = client.post(
            "/api/v1/dispatch",
            json={
                "brand": "HaiRobotics",
                "serialNumber": "ACR-001",
                "orderId": "DISPATCH-HAIQ-001",
                "robotType": "ACR",
                "target": "A-01-02",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol"] == "haiq"
        assert data["payload"]["requestId"] == "DISPATCH-HAIQ-001"

    def test_dispatch_quicktron_proprietary(self, client):
        """Dispatch to Quicktron with proprietary protocol."""
        resp = client.post(
            "/api/v1/dispatch",
            json={
                "brand": "Quicktron",
                "serialNumber": "QT-001",
                "orderId": "DISPATCH-QT-001",
                "protocol": "proprietary",
                "target": "STATION-X",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol"] == "rest"
        assert data["payload"]["station"] == "STATION-X"

    def test_dispatch_unknown_brand_returns_501(self, client):
        """Unknown brand returns 501 with available brands list."""
        resp = client.post(
            "/api/v1/dispatch",
            json={
                "brand": "FAKE_ROBOT",
                "serialNumber": "FAKE-001",
                "orderId": "DISPATCH-FAKE-001",
            },
        )
        assert resp.status_code == 501
        data = resp.json()
        assert data["error"] == "unknown_brand"
        assert data["brand"] == "FAKE_ROBOT"
        assert "KUKA" in data["availableBrands"]

    def test_dispatch_mqtt_disconnected_returns_503(self, client):
        """When MQTT is down, dispatch returns 503."""
        from fastapi.testclient import TestClient

        mock_pub = MagicMock()
        mock_pub.is_connected = False

        with patch("main.get_publisher", return_value=mock_pub):
            from main import app

            with TestClient(app) as c:
                resp = c.post(
                    "/api/v1/dispatch",
                    json={
                        "brand": "KUKA",
                        "serialNumber": "KMR-001",
                        "orderId": "DISPATCH-503",
                    },
                )
                assert resp.status_code == 503
                assert "mqtt_disconnected" in resp.text

    def test_dispatch_all_brands_protocol_matrix(self, client):
        """Verify each brand dispatches with correct protocol."""
        test_cases = [
            ("KUKA", {}, "vda5050"),
            ("MiR", {}, "vda5050"),
            ("OTTO", {}, "vda5050"),
            ("GeekPlus", {"robotModel": "M100"}, "vda5050"),
            ("GeekPlus", {"robotModel": "P800"}, "iop"),
            ("HaiRobotics", {"robotType": "HaiPort"}, "vda5050"),
            ("HaiRobotics", {"robotType": "ACR"}, "haiq"),
            ("Quicktron", {}, "vda5050"),
            ("Quicktron", {"protocol": "proprietary"}, "rest"),
        ]
        for brand, extra_fields, expected_protocol in test_cases:
            payload = {
                "brand": brand,
                "serialNumber": f"{brand}-001",
                "orderId": f"DISPATCH-MATRIX-{brand}-{expected_protocol}",
                **extra_fields,
            }
            resp = client.post("/api/v1/dispatch", json=payload)
            assert resp.status_code == 200, f"Failed for {brand}/{expected_protocol}: {resp.text}"
            data = resp.json()
            assert data["protocol"] == expected_protocol, (
                f"{brand}: expected {expected_protocol}, got {data['protocol']}"
            )

    def test_dispatch_missing_brand_validation(self, client):
        """Missing brand field returns 422 (Pydantic validation)."""
        resp = client.post(
            "/api/v1/dispatch",
            json={
                "serialNumber": "KMR-001",
                "orderId": "DISPATCH-NO-BRAND",
            },
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Part 4: Version compatibility check in dispatch flow
# ═══════════════════════════════════════════════════════════════════════════


class TestVersionCompatCheck:
    """v4.1 verification matrix item 3: version compatibility."""

    def test_all_brands_pass_min_version(self):
        """All registered brands must support VDA5050 >= 1.1.0."""
        from strategies import get_registry
        from strategies.base import MIN_VDA5050_VERSION

        registry = get_registry()
        for brand in registry.list_brands():
            strategy = registry.get(brand)
            assert strategy.check_version_compatibility(MIN_VDA5050_VERSION), (
                f"{brand} does not support VDA5050 >= {MIN_VDA5050_VERSION}"
            )

    def test_version_compat_kuka(self):
        """KUKA supports v2.0.0 which is >= 1.1.0."""
        from strategies.kuka import KukaStrategy

        assert KukaStrategy().check_version_compatibility("1.1.0") is True
        assert KukaStrategy().check_version_compatibility("2.0.0") is True

    def test_version_compat_mir(self):
        """MiR supports v1.1.0 exactly."""
        from strategies.mir import MirStrategy

        assert MirStrategy().check_version_compatibility("1.1.0") is True
        assert MirStrategy().check_version_compatibility("2.0.0") is False

    def test_version_compat_geekplus_dual(self):
        """Geek+ supports both v1.1.0 and v2.0.0."""
        from strategies.geekplus import GeekPlusStrategy

        s = GeekPlusStrategy()
        assert s.check_version_compatibility("1.1.0") is True
        assert s.check_version_compatibility("2.0.0") is True
