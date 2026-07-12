"""Tests for WM backend — SAP Classic WM RFC integration with mock pyrfc."""

from unittest.mock import MagicMock, patch

import pytest
from models.warehouse_task import WarehouseTask


@pytest.fixture
def backend():
    """Create WmBackend with pyrfc mocked — no real SAP needed.

    Patches _create_connection to avoid pyrfc dependency.
    """
    from backends.wm_backend import WmBackend as _WmBackend
    with patch.object(_WmBackend, "_create_connection") as mock_create:
        mock_create.return_value = MagicMock()
        yield _WmBackend(config={
            "rfc_ashost": "mock-host",
            "rfc_sysnr": "00",
            "rfc_client": "800",
            "rfc_user": "testuser",
            "password": "testpass",
        })


@pytest.fixture
def sample_wm_task() -> WarehouseTask:
    """Sample warehouse task for WM backend tests."""
    return WarehouseTask(
        source_system="WM",
        warehouse="001",
        external_id="1000001",
        item_no="0001",
        task_type="PICK",
        source_bin="001-AA-01",
        dest_bin="002-BB-02",
        product="MAT-A",
        batch="BATCH01",
        target_qty=5.0,
        uom="EA",
        status="0",
        vendor_data={
            "plant": "1000",
            "storage_location": "0001",
            "movement_type": "201",
            "transfer_type": "A",
        },
    )


class TestWmBackend:
    """SAP Classic WM (LE-WM) backend tests with mocked RFC."""

    def test_backend_type(self, backend):
        assert backend.backend_type == "wm"

    def test_display_name(self, backend):
        assert "WM" in backend.display_name
        assert "Classic" in backend.display_name

    def test_check_connection_success(self, backend):
        """RFC_PING should return connected=True."""
        status = backend.check_connection()
        assert status["connected"] is True
        assert status["backend"] == "wm"
        assert status["details"]["host"] is not None

    def test_check_connection_pyrfc_not_installed(self):
        """If pyrfc ImportError, check_connection should report not connected."""
        from backends.wm_backend import WmBackend
        bk = WmBackend(config={"rfc_user": "u", "password": "p", "rfc_ashost": "h"})
        with patch.object(bk, "_create_connection") as mock_create:
            mock_create.side_effect = ImportError("No module named pyrfc")
            status = bk.check_connection()
            assert status["connected"] is False
            assert "pyrfc" in status.get("error", "").lower()

    def test_check_connection_pyrfc_connection_error(self):
        """If pyrfc connection fails, check_connection should handle gracefully."""
        from backends.wm_backend import WmBackend
        bk = WmBackend(config={"rfc_user": "u", "password": "p", "rfc_ashost": "h"})
        with patch.object(bk, "_create_connection") as mock_create:
            mock_create.side_effect = RuntimeError("connection refused")
            status = bk.check_connection()
            assert status["connected"] is False
            assert "connection refused" in status.get("error", "")

    def test_list_tasks_empty(self, backend):
        """list_tasks with no results should return empty list."""
        backend._call_rfc = MagicMock(return_value={})
        tasks = backend.list_tasks(warehouse="001", status="0", top=10)
        assert isinstance(tasks, list)
        assert len(tasks) == 0

    def test_list_tasks_with_headers(self, backend):
        """list_tasks should parse TO headers from mock RFC response."""
        backend._call_rfc = MagicMock(side_effect=[
            # First call: L_TO_READ returns headers
            {
                "T_HEADERS": [
                    {"TANUM": "1000001", "STATUS": "0", "BWLVS": "201", "TRART": "A",
                     "MATNR": "MAT-A", "VLPLA": "001-AA-01", "NLPLA": "002-BB-02",
                     "ANFME": 5.0, "ALTME": "EA", "CHARG": "BATCH01",
                     "WERKS": "1000", "LGORT": "0001"},
                ],
                "T_ITEMS": [],
            },
            # Second call: get TO items for 1000001 (no items)
            {"T_ITEMS": [], "T_HEADERS": []},
        ])
        tasks = backend.list_tasks(warehouse="001", status="0", top=10)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.external_id == "1000001"
        assert t.task_type == "PICK"
        assert t.product == "MAT-A"
        assert t.source_bin == "001-AA-01"
        assert t.dest_bin == "002-BB-02"
        assert t.target_qty == 5.0
        assert t.uom == "EA"
        assert t.source_system == "WM"

    def test_get_task_found(self, backend):
        """get_task should return WarehouseTask for existing TO."""
        # Items need BWLVS too for task_type mapping
        backend._call_rfc = MagicMock(return_value={
            "T_HEADERS": [
                {"TANUM": "1000001", "STATUS": "0", "BWLVS": "201",
                 "VLPLA": "001-AA-01", "NLPLA": "002-BB-02", "MATNR": "MAT-A",
                 "ANFME": 5.0, "ALTME": "EA", "WERKS": "1000", "LGORT": "0001"},
            ],
            "T_ITEMS": [
                {"TANUM": "1000001", "TAPOS": "0001", "MATNR": "MAT-A",
                 "BWLVS": "201", "ANFME": 5.0},
            ],
        })
        task = backend.get_task("001", "1000001")
        assert task is not None
        assert task.external_id == "1000001"
        assert task.task_type == "PICK"  # BWLVS 201 -> PICK

    def test_get_task_not_found(self, backend):
        """get_task should return None for missing TO."""
        backend._call_rfc = MagicMock(return_value={"T_HEADERS": [], "T_ITEMS": []})
        task = backend.get_task("001", "9999999")
        assert task is None

    def test_create_task_success(self, backend, sample_wm_task):
        """create_task should return updated task with TO number."""
        backend._call_rfc = MagicMock(return_value={"E_TANUM": "2000001"})
        result = backend.create_task(sample_wm_task)
        assert result is not None
        assert result.external_id == "2000001"
        assert result.to_number == "2000001"

    def test_create_task_failure(self, backend, sample_wm_task):
        """create_task should return None on RFC error."""
        backend._call_rfc = MagicMock(return_value={"E_TANUM": ""})
        result = backend.create_task(sample_wm_task)
        assert result is None

    def test_confirm_task_success(self, backend):
        """confirm_task should return True on RFC success."""
        backend._call_rfc = MagicMock(return_value={})
        ok = backend.confirm_task("001", "1000001", qty=5.0)
        assert ok is True

    def test_confirm_task_failure(self, backend):
        """confirm_task should return False on RFC error."""
        backend._call_rfc = MagicMock(side_effect=RuntimeError("RFC error"))
        ok = backend.confirm_task("001", "1000001", qty=5.0)
        assert ok is False

    def test_cancel_task_success(self, backend):
        """cancel_task should return True on RFC success."""
        backend._call_rfc = MagicMock(return_value={})
        ok = backend.cancel_task("001", "1000001")
        assert ok is True

    def test_cancel_task_failure(self, backend):
        """cancel_task should return False on RFC error."""
        backend._call_rfc = MagicMock(side_effect=RuntimeError("RFC error"))
        ok = backend.cancel_task("001", "1000001")
        assert ok is False

    def test_validate_config_missing_fields(self):
        """validate_config should report missing RFC connection params."""
        from backends.wm_backend import WmBackend
        bk = WmBackend(config={})  # No config
        errors = bk.validate_config()
        assert len(errors) >= 3
        assert any("ashost" in e for e in errors)
        assert any("user" in e for e in errors)
        assert any("password" in e for e in errors)

    def test_validate_config_ok(self, backend):
        """validate_config should return empty list when all fields present."""
        errors = backend.validate_config()
        assert len(errors) == 0

    def test_rfc_retry_on_failure(self, backend):
        """_call_rfc should retry on transient errors (retry is inside _call_rfc)."""
        # Retry logic is built into _call_rfc. Here we verify create_task
        # handles all exceptions from _call_rfc gracefully.
        backend._call_rfc = MagicMock(side_effect=RuntimeError("RFC error"))
        task = WarehouseTask(
            source_system="WM", warehouse="001", external_id="T1",
            target_qty=1.0,
        )
        result = backend.create_task(task)
        assert result is None  # Error handled, no crash

    def test_extract_table_list(self, backend):
        """_extract_table should handle list format."""
        from backends.wm_backend import WmBackend as _W
        result = _W._extract_table({"items": [1, 2, 3]}, "items", [])
        assert result == [1, 2, 3]

    def test_extract_table_missing(self, backend):
        """_extract_table should return default for missing key."""
        from backends.wm_backend import WmBackend as _W
        result = _W._extract_table({}, "nonexistent", [])
        assert result == []

    def test_derive_transfer_type(self, backend):
        from backends.wm_backend import WmBackend as _W
        assert _W._derive_transfer_type("PICK") == "A"
        assert _W._derive_transfer_type("PUT") == "E"
        assert _W._derive_transfer_type("MOVE") == "U"
        assert _W._derive_transfer_type("CHARGE") == "U"
        assert _W._derive_transfer_type("UNKNOWN") == "U"

    def test_get_source_type_prefix(self, backend):
        from backends.wm_backend import WmBackend as _W
        assert _W._get_source_type_prefix("001-AA-01") == "001"
        assert _W._get_source_type_prefix("AB") == "001"  # too short
        assert _W._get_source_type_prefix(None) == "001"
        assert _W._get_source_type_prefix("XYZ-123") == "XYZ"

    def test_connection_ttl_reconnect(self, backend):
        """_get_connection should reconnect after TTL expiry."""
        old_conn = backend._last_conn = MagicMock()
        backend._last_conn_time = 0  # Force expiry
        backend._conn_ttl = 300
        import time
        backend._last_conn_time = time.time() - 600  # 10 min ago → expired
        backend._create_connection = MagicMock(return_value=MagicMock())
        conn = backend._get_connection()
        assert conn is not None
        assert conn != old_conn  # Should be a new connection

    def test_build_conn_params_from_file(self, backend):
        """_build_conn_params should read password from file if not in config."""
        from backends.wm_backend import WmBackend
        bk = WmBackend(config={"password_file": "/nonexistent/pw"})
        params = bk._build_conn_params()
        assert "passwd" in params

    def test_invalid_warehouse_handling(self, backend):
        """list_tasks should not crash with invalid warehouse."""
        # Simulate RFC exception for invalid warehouse
        backend._call_rfc = MagicMock(side_effect=RuntimeError("Warehouse 999 not found"))
        tasks = backend.list_tasks(warehouse="999")
        assert tasks == []


class TestWmBackendHttpMode:
    """WM backend in HTTP mode (uses WM Simulator)."""

    @pytest.fixture
    def http_backend(self):
        from backends.wm_backend import WmBackend
        bk = WmBackend(config={
            "mode": "http",
            "simulator_url": "http://mock-simulator:8001",
            "rfc_ashost": "", "rfc_sysnr": "", "rfc_client": "",
        })
        return bk

    def test_backend_type(self, http_backend):
        assert http_backend.backend_type == "wm"
        assert "Simulator" in http_backend.display_name

    def test_http_mode_validate_config(self, http_backend):
        """HTTP mode should not require RFC params."""
        errors = http_backend.validate_config()
        assert len(errors) == 0

    def test_http_health_check_success(self, http_backend):
        """Health check should connect to simulator."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"tos_created": 5}

        with patch.object(http_backend, "_get_http_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.get.return_value = mock_resp

            status = http_backend.check_connection()
            assert status["connected"] is True
            assert status["mode"] == "http"
            assert status["details"]["tos_created"] == 5

    def test_http_health_check_fail(self, http_backend):
        """Health check should return not connected on error."""
        with patch.object(http_backend, "_get_http_client") as mock_get:
            mock_get.side_effect = RuntimeError("connection refused")
            status = http_backend.check_connection()
            assert status["connected"] is False
            assert status["mode"] == "http"

    def test_http_list_tasks(self, http_backend):
        """list_tasks via HTTP simulator."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "T_HEADERS": [
                {"TANUM": "5000001", "STATUS": "0", "BWLVS": "201", "TRART": "A",
                 "MATNR": "MAT-HTTP", "VLPLA": "X1-01", "NLPLA": "Y2-02",
                 "ANFME": 7.0, "ALTME": "EA", "CHARG": "B-001",
                 "WERKS": "1000", "LGORT": "0001"},
            ],
            "T_ITEMS": [],
        }

        with patch.object(http_backend, "_get_http_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.post.return_value = mock_resp

            tasks = http_backend.list_tasks(warehouse="001", status="0", top=10)
            assert len(tasks) == 1
            t = tasks[0]
            assert t.external_id == "5000001"
            assert t.task_type == "PICK"
            assert t.product == "MAT-HTTP"

    def test_http_create_confirm_cancel(self, http_backend):
        """Full CRUD flow via HTTP simulator."""
        from models.warehouse_task import WarehouseTask

        mock_resp_create = MagicMock()
        mock_resp_create.json.return_value = {"E_TANUM": "6000001"}

        mock_resp_ok = MagicMock()
        mock_resp_ok.json.return_value = {"E_SUBRC": 0}

        with patch.object(http_backend, "_get_http_client") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.post.side_effect = [
                mock_resp_create,
                mock_resp_ok,
                mock_resp_ok,
            ]

            task = WarehouseTask(
                source_system="WM", warehouse="001",
                external_id="", task_type="PUT",
                source_bin="A1", dest_bin="B2",
                product="MAT-C", target_qty=2.0,
            )
            created = http_backend.create_task(task)
            assert created is not None
            assert created.external_id == "6000001"

            confirmed = http_backend.confirm_task("001", "6000001", qty=2.0)
            assert confirmed is True

            cancelled = http_backend.cancel_task("001", "6000001")
            assert cancelled is True
