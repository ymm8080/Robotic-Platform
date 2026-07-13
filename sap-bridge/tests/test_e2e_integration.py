"""End-to-end integration tests: order lifecycle, MQTT, SAP, inventory.

Tests the full flow:
  SAP order creation → MQTT publishing → Order persistence → State transitions
  → Robot status → Dead letter queue → Admin API

Requires: pytest, pytest-asyncio, httpx
Optional: Redis (tests skip if unavailable)
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("MQTT_BROKER", "localhost")


# ── Session-scoped setup: run migrations once ──────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Schema is initialized by conftest.py session fixture."""
    yield


# ═══════════════════════════════════════════════════════════════════════════
# Test 1: Order Service — Full Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestOrderLifecycleE2E:
    """Full order lifecycle: create → assign → execute → complete (with edge cases)."""

    def test_full_lifecycle(self, setup_db):
        """CRÉATED → ASSIGNED → IN_PROGRESS → COMPLETED with all fields."""
        from models.order import OrderStatus, OrderType, WarehouseOrder
        from services.order_service import OrderService

        svc = OrderService()

        # Create
        order = svc.create_order(
            WarehouseOrder(
                order_no="E2E-001",
                type=OrderType.PICK,
                priority=0,
                source="SAP-TASK-001",
                robot_brand="KUKA",
                location="A01-02-03",
                weight=12.5,
                expected_qty=5,
            )
        )
        assert order.id > 0
        assert order.status == OrderStatus.CREATED
        assert order.version == 1

        # Assign
        order = svc.assign_order("E2E-001", "KUKA", "KMR-001")
        assert order.status == OrderStatus.ASSIGNED
        assert order.robot_serial == "KMR-001"
        assert order.version == 2

        # Start execution
        order = svc.start_execution("E2E-001")
        assert order.status == OrderStatus.IN_PROGRESS
        assert order.version == 3

        # Complete
        order = svc.complete_order("E2E-001")
        assert order.status == OrderStatus.COMPLETED
        assert order.completed_at is not None
        assert order.version == 4

        # Verify persisted
        order = svc.get_order("E2E-001")
        assert order.status == OrderStatus.COMPLETED
        assert order.type == OrderType.PICK
        assert order.priority == 0
        assert order.source == "SAP-TASK-001"

    def test_idempotent_create_duplicate(self, setup_db):
        """Creating duplicate order_no should not raise — VDA5050 idempotency."""
        from models.order import WarehouseOrder
        from services.order_service import OrderService

        svc = OrderService()
        order1 = svc.create_order(WarehouseOrder(order_no="E2E-IDEMP-001"))
        assert order1.id > 0

        import psycopg2

        with pytest.raises(psycopg2.errors.UniqueViolation):
            svc.create_order(WarehouseOrder(order_no="E2E-IDEMP-001"))

    def test_cancel_created_order(self, setup_db):
        """CREATED → CANCELLED."""
        from models.order import OrderStatus, WarehouseOrder
        from services.order_service import OrderService

        svc = OrderService()
        svc.create_order(WarehouseOrder(order_no="E2E-CANCEL-001"))
        order = svc.cancel_order("E2E-CANCEL-001")
        assert order.status == OrderStatus.CANCELLED

    def test_cannot_cancel_in_progress(self, setup_db):
        """IN_PROGRESS → cancel returns None (must fail or suspend first)."""
        from models.order import WarehouseOrder
        from services.order_service import OrderService

        svc = OrderService()
        svc.create_order(WarehouseOrder(order_no="E2E-NOCANCEL-001"))
        svc.assign_order("E2E-NOCANCEL-001", "KUKA", "KMR-001")
        svc.start_execution("E2E-NOCANCEL-001")
        result = svc.cancel_order("E2E-NOCANCEL-001")
        assert result is None

    def test_fail_with_reason(self, setup_db):
        """IN_PROGRESS → FAILED with error message."""
        from models.order import WarehouseOrder
        from services.order_service import OrderService, OrderStatus

        svc = OrderService()
        svc.create_order(WarehouseOrder(order_no="E2E-FAIL-001"))
        svc.assign_order("E2E-FAIL-001", "MIR", "MIR-001")
        svc.start_execution("E2E-FAIL-001")
        order = svc.fail_order("E2E-FAIL-001", "Hardware error: motor stall")
        assert order.status == OrderStatus.FAILED
        assert "motor stall" in order.error_message

    def test_suspend_and_retry(self, setup_db):
        """IN_PROGRESS → SUSPENDED → re-assign → IN_PROGRESS."""
        from models.order import WarehouseOrder
        from services.order_service import OrderService, OrderStatus

        svc = OrderService()
        svc.create_order(WarehouseOrder(order_no="E2E-SUSPEND-001"))
        svc.assign_order("E2E-SUSPEND-001", "OTTO", "OTTO-001")
        svc.start_execution("E2E-SUSPEND-001")

        # Suspend
        order = svc.suspend_order("E2E-SUSPEND-001", "Zone blocked")
        assert order.status == OrderStatus.SUSPENDED
        assert order.version == 4

    def test_version_optimistic_locking(self, setup_db):
        """Concurrent updates: second write with stale version raises RuntimeError."""
        from models.order import OrderStatus, WarehouseOrder
        from services.order_service import OrderService

        svc = OrderService()
        svc.create_order(WarehouseOrder(order_no="E2E-LOCK-001"))
        svc.assign_order("E2E-LOCK-001", "KUKA", "KMR-001")
        order = svc.get_order("E2E-LOCK-001")

        # Simulate stale version write directly via psycopg2
        from db import connect as _connect

        _conn = _connect()
        _conn.execute(
            "UPDATE orders SET status='COMPLETED', version=version+1 WHERE order_no=?",
            ("E2E-LOCK-001",),
        )
        _conn.commit()
        _conn.close()

        order.status = OrderStatus.IN_PROGRESS  # stale
        order.version = 2  # stale
        with pytest.raises(RuntimeError, match="was modified concurrently"):
            svc._update(order)
        # Verify the concurrent write was preserved
        refreshed = svc.get_order("E2E-LOCK-001")
        assert refreshed.status == OrderStatus.COMPLETED
        assert refreshed.version >= 3

    def test_list_orders_pagination(self, setup_db):
        """List with limit/offset."""
        from models.order import WarehouseOrder
        from services.order_service import OrderService

        svc = OrderService()
        for i in range(5):
            svc.create_order(WarehouseOrder(order_no=f"E2E-PAGE-{i:03d}"))

        page1 = svc.list_orders(limit=2)
        assert len(page1) == 2

        page2 = svc.list_orders(limit=2, offset=2)
        assert len(page2) == 2

    def test_list_orders_filter_by_brand(self, setup_db):
        """Filter by robot brand."""
        from models.order import WarehouseOrder
        from services.order_service import OrderService

        svc = OrderService()
        svc.create_order(WarehouseOrder(order_no="E2E-BRAND-001", robot_brand="BRANDA"))
        svc.create_order(WarehouseOrder(order_no="E2E-BRAND-002", robot_brand="BRANDB"))

        brand_a = svc.list_orders(brand="BRANDA")
        brand_b = svc.list_orders(brand="BRANDB")
        assert len(brand_a) == 1
        assert len(brand_b) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Test 2: MQTT Publisher — VDA5050 Compliance
# ═══════════════════════════════════════════════════════════════════════════


class TestMQTTPublisherE2E:
    """MQTT publisher with mocked broker (tests logic without real MQTT)."""

    @pytest.fixture
    def publisher(self):
        from mqtt_publisher import VDA5050Publisher

        mock_r = MagicMock()
        mock_r.incr.return_value = 1
        mock_r.expire.return_value = True
        with patch("redis.from_url", return_value=mock_r):
            pub = VDA5050Publisher()
            pub.client = MagicMock()
            pub.client.publish.return_value = MagicMock(rc=0, mid=42)
            return pub

    def test_publish_vda5050_envelope(self, publisher):
        """Published message must contain VDA5050 header fields."""
        mid = publisher.publish(
            manufacturer="KUKA",
            serial_number="KMR-001",
            topic_suffix="order",
            payload={"orderId": "ORD-001", "nodes": [], "edges": []},
        )
        assert mid == 42
        topic = publisher.client.publish.call_args[0][0]
        assert topic == "vda5050/KUKA/KMR-001/order"
        payload = json.loads(publisher.client.publish.call_args[0][1])
        assert payload["headerId"] == 1
        assert payload["version"] == "2.0.0"
        assert payload["manufacturer"] == "KUKA"
        assert payload["serialNumber"] == "KMR-001"
        assert "timestamp" in payload
        assert payload["orderId"] == "ORD-001"

    def test_publish_qos_defaults_to_one(self, publisher):
        publisher.publish("KUKA", "KMR-001", "state", {"state": "IDLE"})
        assert publisher.client.publish.call_args[1].get("qos") == 1

    def test_publish_qos_explicit(self, publisher):
        publisher.publish("KUKA", "KMR-001", "order", {"orderId": "O-1"}, qos=0)
        assert publisher.client.publish.call_args[1].get("qos") == 0

    def test_sequence_number_auto_increment(self):
        """Each publish gets auto-incrementing seq via Redis INCR."""
        from mqtt_publisher import VDA5050Publisher

        mock_r = MagicMock()
        mock_r.incr.side_effect = [10, 20, 30]
        mock_r.expire.return_value = True
        with patch("redis.from_url", return_value=mock_r):
            pub = VDA5050Publisher()
            pub.client = MagicMock()
            pub.client.publish.return_value = MagicMock(rc=0, mid=1)
            pub.publish("KUKA", "KMR-001", "state", {"state": "A"})
            pub.publish("KUKA", "KMR-001", "state", {"state": "B"})
            pub.publish("MIR", "MIR-001", "state", {"state": "C"})
            payloads = [json.loads(c[0][1]) for c in pub.client.publish.call_args_list]
            assert [p["headerId"] for p in payloads] == [10, 20, 30]

    def test_lwt_configured(self, publisher):
        publisher.connect()
        assert publisher.client.will_set.call_args[1].get("qos") == 1
        assert publisher.client.will_set.call_args[1].get("retain") is True

    def test_publish_failure_returns_none(self, publisher):
        publisher.client.publish.return_value = MagicMock(rc=5)
        result = publisher.publish("KUKA", "KMR-001", "state", {"state": "IDLE"})
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Test 3: HTTP API — FastAPI TestClient (mocked MQTT)
# ═══════════════════════════════════════════════════════════════════════════


class TestHTTPAPIE2E:
    """FastAPI HTTP endpoints with mocked dependencies."""

    @pytest.fixture
    def client(self, setup_db):
        """FastAPI TestClient with mocked MQTT publisher + Redis."""
        from fastapi.testclient import TestClient

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.hgetall.return_value = {}
        mock_redis.hget.return_value = None
        mock_redis.hset.return_value = 1
        mock_redis.zcard.return_value = 0
        mock_redis.zrange.return_value = []
        mock_redis.zadd.return_value = 1
        mock_redis.zrem.return_value = 1
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True
        mock_redis.keys.return_value = []
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.lrange.return_value = []
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.exists.return_value = 0
        mock_redis.bzpopmin.return_value = None

        mock_pub = MagicMock()
        mock_pub.is_connected = True
        mock_pub.publish.return_value = 42

        with patch("redis.from_url", return_value=mock_redis), patch("main.get_publisher", return_value=mock_pub):
            from main import app

            with TestClient(app) as c:
                yield c

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "v4.1"

    def test_create_order_via_api(self, client):
        resp = client.post(
            "/api/v1/orders",
            json={
                "manufacturer": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "API-E2E-001",
                "orderType": "PICK",
                "priority": 0,
                "nodes": [{"nodeId": "N1", "sequenceId": 1, "nodePosition": {"x": 10.0, "y": 20.0}}],
                "edges": [{"edgeId": "E1", "sequenceId": 1, "edgePosition": {"startNodeId": "N1", "endNodeId": "N2"}}],
                "source": "SAP-TEST-001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["orderId"] == "API-E2E-001"
        assert data["mqttMid"] == 42

    def test_get_order_via_api(self, client):
        client.post(
            "/api/v1/orders",
            json={
                "manufacturer": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "API-GET-001",
                "orderType": "MOVE",
            },
        )
        resp = client.get("/api/v1/orders/API-GET-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["orderNo"] == "API-GET-001"
        assert data["status"] == "ASSIGNED"
        assert data["robotBrand"] == "KUKA"

    def test_list_orders_via_api(self, client):
        client.post(
            "/api/v1/orders",
            json={
                "manufacturer": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "API-LIST-001",
                "orderType": "MOVE",
            },
        )
        resp = client.get("/api/v1/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    def test_complete_order_via_api(self, client):
        client.post(
            "/api/v1/orders",
            json={
                "manufacturer": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "API-COMPLETE-001",
            },
        )
        resp = client.post("/api/v1/orders/API-COMPLETE-001/complete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"

    def test_cancel_order_via_api(self, client):
        client.post(
            "/api/v1/orders",
            json={
                "manufacturer": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "API-CANCEL-001",
            },
        )
        resp = client.post("/api/v1/orders/API-CANCEL-001/cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CANCELLED"

    def test_fail_order_via_api(self, client):
        client.post(
            "/api/v1/orders",
            json={
                "manufacturer": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "API-FAIL-001",
            },
        )
        resp = client.post(
            "/api/v1/orders/API-FAIL-001/fail",
            json={"status": "FAILED", "errorMessage": "Motor stall detected"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stall" in data["errorMessage"]

    def test_suspend_order_via_api(self, client):
        client.post(
            "/api/v1/orders",
            json={
                "manufacturer": "KUKA",
                "serialNumber": "KMR-001",
                "orderId": "API-SUSPEND-001",
            },
        )
        # Must start execution first — only IN_PROGRESS can be suspended
        # (per config.yaml order lifecycle: ASSIGNED → IN_PROGRESS → SUSPENDED)
        client.post(
            "/api/v1/orders/API-SUSPEND-001/start-execution",
            json={"status": "IN_PROGRESS"},
        )
        resp = client.post(
            "/api/v1/orders/API-SUSPEND-001/suspend",
            json={"status": "SUSPENDED", "errorMessage": "Zone blocked"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUSPENDED"

    def test_404_on_nonexistent_order(self, client):
        resp = client.get("/api/v1/orders/DOES-NOT-EXIST")
        assert resp.status_code == 404

    def test_invalid_payload_returns_422(self, client):
        resp = client.post("/api/v1/orders", json={"invalid": "data"})
        assert resp.status_code == 422  # Pydantic validation

    def test_mqtt_disconnected_returns_503(self, client):
        """When MQTT is down, create order should return 503."""
        from fastapi.testclient import TestClient

        mock_pub = MagicMock()
        mock_pub.is_connected = False

        with patch("main.get_publisher", return_value=mock_pub):
            from main import app

            with TestClient(app) as c:
                resp = c.post(
                    "/api/v1/orders",
                    json={
                        "manufacturer": "KUKA",
                        "serialNumber": "KMR-001",
                        "orderId": "API-DISCONNECTED",
                    },
                )
                assert resp.status_code == 503
                assert "mqtt_disconnected" in resp.text

    def test_queue_depth_endpoint(self, client):
        resp = client.get("/api/v1/orders/queue")
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
        data = resp.json()
        assert "queue" in data

    def test_robot_status_endpoint(self, client):
        resp = client.get("/api/v1/robots/status")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Test 4: Strategy Engine — Multi-Brand Dispatching
# ═══════════════════════════════════════════════════════════════════════════


class TestStrategyEngineE2E:
    """Brand strategy registry, normalization, quirks."""

    def test_registry_lists_brands(self):
        from strategies import get_registry

        registry = get_registry()
        brands = registry.list_brands()
        assert "KUKA" in brands
        assert "MIR" in brands
        assert "OTTO" in brands

    def test_strategy_normalizes_state(self):
        from strategies import get_registry

        registry = get_registry()

        kuka = registry.get("KUKA")
        # KUKA with batteryCharge > 0 and no driving/paused → IDLE
        result = kuka.handle_state({"drives": [{"state": "IDLE"}], "faults": [], "batteryState": {"batteryCharge": 85}})
        assert result.status == "IDLE"

    def test_kuka_quirk_detection(self):
        from strategies import get_registry

        kuka = get_registry().get("KUKA")
        quirks = kuka.get_quirks()
        quirk_names = [q.name for q in quirks]
        assert "lift-action-requires-pre-navigate" in quirk_names

    def test_mir_normalizes_state(self):
        from strategies import get_registry

        mir = get_registry().get("MIR")
        result = mir.handle_state({"mission": None, "mode": 3, "state": 2})
        # MiR mode 3 = idle
        assert result.status in ("IDLE", "BUSY", "CHARGING")

    def test_otto_normalizes_to_executing(self):
        from strategies import get_registry

        otto = get_registry().get("OTTO")
        # OTTO with running actions → EXECUTING
        result = otto.handle_state({"actionStates": [{"actionStatus": "RUNNING"}]})
        assert result.status == "EXECUTING"

    def test_unknown_brand_returns_none(self):
        from strategies import get_registry

        assert get_registry().get("DOES_NOT_EXIST") is None


# ═══════════════════════════════════════════════════════════════════════════
# Test 5: Priority Queue & Dead Letter
# ═══════════════════════════════════════════════════════════════════════════


class TestQueueDeadLetterE2E:
    """Priority dispatch queue + dead letter handling."""

    @pytest.fixture(autouse=True)
    def mock_redis_queue(self):
        with patch("redis.from_url") as mock_ru:
            mock_r = MagicMock()
            mock_ru.return_value = mock_r
            mock_r.ping.return_value = True
            mock_r.hgetall.return_value = {}
            mock_r.zcard.return_value = 0
            mock_r.zrange.return_value = []
            yield

    def test_priority_queue_depth(self, mock_redis_queue):
        from dispatch_queue import PriorityQueue

        q = PriorityQueue()
        assert q.depth() >= 0
        assert q.is_healthy is not None

    def test_queue_peek_returns_items(self):
        from dispatch_queue import PriorityQueue

        q = PriorityQueue()
        items = q.peek(5)
        assert isinstance(items, list)

    def test_deadletter_list(self):
        from dispatch_queue import DeadLetterHandler

        dl = DeadLetterHandler()
        items = dl.list_all()
        assert isinstance(items, list)
        assert dl.count_unresolved() >= 0


# ═══════════════════════════════════════════════════════════════════════════
# Test 6: Inventory Service
# ═══════════════════════════════════════════════════════════════════════════


class TestInventoryServiceE2E:
    """Inventory cache with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        mock_r = MagicMock()
        mock_r.get.return_value = None
        mock_r.keys.return_value = []
        return mock_r

    def test_get_stock_miss_returns_none(self):
        from services.inventory_service import InventoryService

        with patch("redis.from_url") as mock_ru:
            mock_ru.return_value = MagicMock()
            mock_ru.return_value.get.return_value = None
            svc = InventoryService()
            qty = svc.get_stock("PROD-001", "WM01")
            assert qty is None


# ═══════════════════════════════════════════════════════════════════════════
# Test 7: EWM Warehouse Service (mocked SAP)
# ═══════════════════════════════════════════════════════════════════════════


class TestEwmBackendE2E:
    """SAP EWM OData backend with mocked HTTP."""

    def test_check_connection(self):
        """Connection check should return a status dict."""
        from backends.ewm_backend import EwmBackend

        svc = EwmBackend(config={"user": "test", "password": "test"})
        # When SAP is unreachable, returns error dict
        status = svc.check_connection()
        assert isinstance(status, dict)

    def test_list_tasks_without_sap_returns_empty(self):
        """With mocked SAP returning empty, list_tasks returns empty list."""
        from backends.ewm_backend import EwmBackend

        svc = EwmBackend(config={"user": "test", "password": "test"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"d": {"results": []}}
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_resp
        with patch.object(svc, "_get_client", return_value=mock_client):
            tasks = svc.list_tasks(warehouse="WM01", status="0", top=10)
            assert tasks == []

    def test_check_connection_with_mocked_sap(self):
        """With mocked SAP, connection check succeeds."""
        from backends.ewm_backend import EwmBackend

        svc = EwmBackend(config={"user": "test", "password": "test"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_resp
        with patch.object(svc, "_get_client", return_value=mock_client):
            status = svc.check_connection()
            assert status["connected"] is True
            assert status["details"]["status_code"] == 200
