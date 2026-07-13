"""Tests for EWM backend — SAP OData integration."""

from unittest.mock import MagicMock, patch

import pytest

# ── Fixture for EWM backend with Redis mocked ─────────────────────────


@pytest.fixture
def backend():
    """Create EwmBackend with Redis CSRF token manager mocked."""
    with patch("backends.ewm_backend.rd.from_url") as mock_ru:
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # No cached CSRF token
        mock_ru.return_value = mock_redis
        from backends.ewm_backend import EwmBackend

        yield EwmBackend(config={"user": "test", "password": "test"})


class TestEwmBackend:
    """SAP EWM OData backend tests with mocked HTTP."""

    def test_backend_type(self, backend):
        assert backend.backend_type == "ewm"

    def test_display_name(self, backend):
        assert "EWM" in backend.display_name

    def test_check_connection_success(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(backend, "_get_client") as mock_get:
            mock_get.return_value.__enter__.return_value.get.return_value = mock_resp
            status = backend.check_connection()
            assert status["connected"] is True
            assert status["backend"] == "ewm"

    def test_check_connection_401(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch.object(backend, "_get_client") as mock_get:
            mock_get.return_value.__enter__.return_value.get.return_value = mock_resp
            status = backend.check_connection()
            assert status["connected"] is False

    def test_check_connection_exception(self, backend):
        with patch.object(backend, "_get_client", side_effect=ConnectionError("SAP down")):
            status = backend.check_connection()
            assert status["connected"] is False

    def test_list_tasks_success(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "d": {
                "results": [
                    {"Tanum": "TASK-001", "Matnr": "MAT-A"},
                    {"Tanum": "TASK-002", "Matnr": "MAT-B"},
                ]
            }
        }
        with patch.object(backend, "_get_client") as mock_get:
            mock_get.return_value.__enter__.return_value.get.return_value = mock_resp
            tasks = backend.list_tasks(warehouse="WM01", status="0", top=10)
            assert len(tasks) == 2
            assert tasks[0].source_system == "EWM"

    def test_list_tasks_empty(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"d": {"results": []}}
        with patch.object(backend, "_get_client") as mock_get:
            mock_get.return_value.__enter__.return_value.get.return_value = mock_resp
            tasks = backend.list_tasks(warehouse="WM01", status="0", top=10)
            assert tasks == []

    def test_get_task_not_found(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch.object(backend, "_get_client") as mock_get:
            mock_get.return_value.__enter__.return_value.get.return_value = mock_resp
            task = backend.get_task("WM01", "DOES_NOT_EXIST")
            assert task is None

    def test_confirm_task_success(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with (
            patch.object(backend, "_get_csrf_headers", return_value={}),
            patch.object(backend, "_get_client") as mock_get,
        ):
            mock_get.return_value.__enter__.return_value.post.return_value = mock_resp
            result = backend.confirm_task("WM01", "TASK-001", qty=5.0)
            assert result is True

    def test_confirm_task_failure(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with (
            patch.object(backend, "_get_csrf_headers", return_value={}),
            patch.object(backend, "_get_client") as mock_get,
        ):
            mock_get.return_value.__enter__.return_value.post.return_value = mock_resp
            result = backend.confirm_task("WM01", "TASK-001", qty=10.0)
            assert result is False

    def test_cancel_task_success(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with (
            patch.object(backend, "_get_csrf_headers", return_value={}),
            patch.object(backend, "_get_client") as mock_get,
        ):
            mock_get.return_value.__enter__.return_value.post.return_value = mock_resp
            result = backend.cancel_task("WM01", "TASK-001")
            assert result is True

    def test_create_task_returns_task(self, backend):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"d": {"Tanum": "NEW-TASK", "Matnr": "MAT-A"}}

        from models.warehouse_task import WarehouseTask

        task = WarehouseTask(
            source_system="EWM",
            warehouse="WM01",
            external_id="NEW-TASK",
            item_no="0001",
            product="MAT-A",
        )

        with (
            patch.object(backend, "_get_csrf_headers", return_value={}),
            patch.object(backend, "_get_client") as mock_get,
        ):
            mock_get.return_value.__enter__.return_value.post.return_value = mock_resp
            result = backend.create_task(task)
            assert result is not None

    def test_validate_config(self, backend):
        errors = backend.validate_config()
        assert isinstance(errors, list)

    def test_parse_task_maps_fields(self, backend):
        raw = {
            "EWMWarehouse": "WM01",
            "WarehouseTask": "TASK-001",
            "WarehouseTaskItem": "0001",
            "WarehouseProcessType": "PICK",
            "ProductName": "MAT-A",
            "TargetQuantityInBaseUnit": "10",
            "SourceStorageBin": "BIN-01",
            "DestinationStorageBin": "BIN-02",
        }
        task = backend._parse_task(raw)
        assert task.external_id == "TASK-001"
        assert task.task_type == "PICK"
        assert task.product == "MAT-A"
        assert task.target_qty == 10.0
