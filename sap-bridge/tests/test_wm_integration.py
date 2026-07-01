"""E2E integration tests: SAP WM backend -> batch -> order -> dispatch flow.

Tests the full pipeline: WM RFC backend -> BatchService -> OrderService -> PriorityQueue.
Uses mocked _create_connection -- no real SAP WM required.
"""

from unittest.mock import MagicMock, patch

import pytest

from models.warehouse_task import WarehouseTask


@pytest.fixture
def wm_backend():
    """Create WmBackend with _create_connection mocked -- no pyrfc needed."""
    from backends.wm_backend import WmBackend
    bk = WmBackend(config={
        "rfc_ashost": "mock-host", "rfc_sysnr": "00",
        "rfc_client": "800", "rfc_user": "test", "password": "test",
    })
    bk._create_connection = MagicMock(return_value=MagicMock())
    # Mock RFC responses for list_tasks
    bk._call_rfc = MagicMock(return_value={
        "T_HEADERS": [
            {"TANUM": "3000001", "STATUS": "0", "BWLVS": "201", "TRART": "A",
             "MATNR": "MAT-A", "VLPLA": "AA-01", "NLPLA": "BB-02",
             "ANFME": 5.0, "ALTME": "EA", "WERKS": "1000", "LGORT": "0001"},
            {"TANUM": "3000002", "STATUS": "0", "BWLVS": "101", "TRART": "E",
             "MATNR": "MAT-B", "VLPLA": "CC-01", "NLPLA": "DD-02",
             "ANFME": 3.0, "ALTME": "EA", "WERKS": "1000", "LGORT": "0001"},
        ],
        "T_ITEMS": [],
    })
    return bk


class TestWmE2EFlow:
    """Full E2E: WM backend -> batch -> order -> queue."""

    def test_wm_backend_type(self, wm_backend):
        assert wm_backend.backend_type == "wm"
        assert "WM" in wm_backend.display_name

    def test_wm_list_tasks(self, wm_backend):
        """list_tasks should return parsed WarehouseTask objects."""
        tasks = wm_backend.list_tasks(warehouse="001", status="0", top=10)
        assert len(tasks) == 2
        assert tasks[0].external_id == "3000001"
        assert tasks[0].task_type == "PICK"   # BWLVS 201 -> PICK
        assert tasks[1].external_id == "3000002"
        assert tasks[1].task_type == "PUT"    # BWLVS 101 -> PUT

    def test_wm_task_model_fields(self, wm_backend):
        """WM tasks should populate WM-specific WarehouseTask fields."""
        tasks = wm_backend.list_tasks(warehouse="001", status="0", top=10)
        t = tasks[0]
        assert t.source_system == "WM"
        assert t.is_wm is True
        assert t.is_ewm is False
        assert t.movement_type == "201"
        assert t.transfer_type == "A"
        assert t.plant == "1000"
        assert t.storage_location == "0001"

    def test_wm_get_task(self, wm_backend):
        """get_task should return single task or None."""
        found = wm_backend.get_task("001", "3000001")
        assert found is not None
        assert found.external_id == "3000001"

        # Mock missing task
        wm_backend._call_rfc = MagicMock(return_value={"T_HEADERS": [], "T_ITEMS": []})
        missing = wm_backend.get_task("001", "9999999")
        assert missing is None

    def test_wm_create_task(self, wm_backend):
        """create_task should return updated task with TO number."""
        wm_backend._call_rfc = MagicMock(return_value={"E_TANUM": "4000001"})
        task = WarehouseTask(
            source_system="WM", warehouse="001", external_id="T1",
            task_type="PICK", source_bin="AA-01", dest_bin="BB-02",
            product="MAT-X", target_qty=3.0, uom="EA",
            vendor_data={"movement_type": "201", "transfer_type": "A"},
        )
        result = wm_backend.create_task(task)
        assert result is not None
        assert result.external_id == "4000001"

    def test_wm_confirm_cancel_flow(self, wm_backend):
        """Confirm and cancel operations on WM backend."""
        wm_backend._call_rfc = MagicMock(return_value={})
        assert wm_backend.confirm_task("001", "3000001", qty=5.0) is True
        assert wm_backend.cancel_task("001", "3000001") is True

        # Failure case
        wm_backend._call_rfc = MagicMock(side_effect=RuntimeError("RFC error"))
        assert wm_backend.confirm_task("001", "3000001", qty=5.0) is False
        assert wm_backend.cancel_task("001", "3000001") is False

    def test_wm_health_check(self, wm_backend):
        """WM backend health check should report connected."""
        status = wm_backend.check_connection()
        assert status["connected"] is True
        assert status["backend"] == "wm"

    def test_wm_to_order_conversion(self, wm_backend, monkeypatch, tmp_path):
        """BatchService._task_to_order should convert WM task to VDA5050 order."""
        monkeypatch.setenv("DB_PATH", str(tmp_path / "robot_platform.db"))
        from services.batch_service import BatchService
        svc = BatchService()
        tasks = wm_backend.list_tasks(warehouse="001", status="0", top=1)
        assert len(tasks) == 1

        order = svc._task_to_order(tasks[0], "WM02")
        assert order is not None
        assert order.order_no == "3000001"
        assert order.source == "SAP:WM02:3000001"

    def test_wm_backend_via_factory(self):
        """Factory should instantiate WmBackend from config."""
        from backends.factory import WarehouseBackendFactory
        from backends.wm_backend import WmBackend
        with patch.object(WmBackend, "_create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            factory = WarehouseBackendFactory()
            factory._config = {
                "sap": {
                    "warehouses": {
                        "WM02": {
                            "backend": "wm",
                            "rfc_ashost": "mock-host",
                            "rfc_sysnr": "00",
                            "rfc_client": "800",
                            "rfc_user": "test",
                            "password": "test",
                        }
                    }
                }
            }
            backend = factory.get_backend("WM02")
            assert backend is not None
            assert backend.backend_type == "wm"

    def test_factory_returns_none_for_unknown_warehouse(self):
        """Factory should return None for unconfigured warehouse."""
        from backends.factory import WarehouseBackendFactory
        factory = WarehouseBackendFactory()
        factory._config = {"sap": {"warehouses": {}}}
        backend = factory.get_backend("NONEXISTENT")
        assert backend is None
