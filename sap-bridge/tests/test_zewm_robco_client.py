"""ZEWM ROBCO client test suite — 10 categories, mocked HTTP + Redis.

Test categories:
  1. Imports            — all public API symbols importable
  2. Success paths      — 8 P0/P1 methods with mocked 200 responses
  3. Exception mapping  — each of 17 RobcoError subclasses raised for SAP errors
  4. CSRF retry         — 403 -> re-fetch CSRF -> retry succeeds
  5. Rate limit         — 429 -> backoff -> retry succeeds
  6. SAP error parsing  — "ROBOT_NOT_FOUND/001" splits to "ROBOT_NOT_FOUND"
  7. Config validation  — missing fields -> errors; valid config -> empty
  8. _parse_response    — unwrap SAP ``{"d": {...}}`` envelope
  9. P2 stubs           — all 4 stubs raise NotImplementedError
  10. map_robot_error_to_exccode — exact match, prefix fallback, no match
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from clients.zewm_robco_client import ZewmRobcoClient
from clients.zewm_robco_exceptions import (
    NoErrorQueueError,
    NoOrderFoundError,
    NoRobotResourceTypeError,
    QueueNotChangedError,
    RobcoError,
    RobcoInternalError,
    RobotHasOrderError,
    RobotNotFoundError,
    StatusNotSetError,
    WarehouseOrderLockedError,
    WhoAssignedError,
    WhoInProcessError,
    WhoLockedError,
    WhoNotFoundError,
    WhoNotUnassignedError,
    WhtAlreadyConfirmedError,
    WhtAssignedError,
    WhtNotConfirmedError,
    raise_for_error_code,
)
from clients.zewm_robco_types import ExceptionCode, map_robot_error_to_exccode

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_redis():
    """Patch ``redis_from_url`` in the client module; return a mock Redis instance
    with pre-cached CSRF values so ``_get_csrf_headers`` avoids a real $metadata fetch."""
    with patch("clients.zewm_robco_client.redis_from_url") as mock_from_url:
        instance = MagicMock()
        mock_from_url.return_value = instance
        # Pre-populate CSRF cache so _get_csrf_headers uses cached values
        instance.get.side_effect = lambda key: {
            "sap:zewm_robco:csrf_token": "mock-csrf-token",
            "sap:zewm_robco:csrf_cookies": "sap-usercontext=mock",
        }.get(key)
        yield instance


@pytest.fixture
def mock_httpx():
    """Patch httpx.Client returning a context-manager compatible mock instance."""
    with patch("httpx.Client") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.__enter__.return_value = instance
        yield instance


@pytest.fixture
def valid_config():
    """Standard valid configuration dict for ZewmRobcoClient."""
    return {
        "enabled": True,
        "base_url": "https://sap-test.example.com:443",
        "client": "100",
        "odata_service": "/sap/opu/odata/sap/ZEWM_ROBCO_SRV",
        "auth_mode": "basic",
        "user": "TEST_USER",
        "password": "test_pass",
        "rate_limit": 80,
        "connection_timeout": 30,
        "redis_url": "redis://localhost:6379/1",
        "confirm_retry_max": 5,
        "confirm_retry_backoff_base": 1,
        "confirm_retry_backoff_cap": 30,
    }


@pytest.fixture
def client(valid_config, mock_redis, mock_httpx):
    """ZewmRobcoClient with mocked HTTP and Redis backends."""
    return ZewmRobcoClient(valid_config)


# ── Helpers ─────────────────────────────────────────────────────────────


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Build a minimal mock ``httpx.Response``."""
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    m.text = str(json_data) if json_data else ""
    return m


# ═══════════════════════════════════════════════════════════════════════
# 1. Imports — all public API symbols importable
# ═══════════════════════════════════════════════════════════════════════


class TestImports:
    """Verify every public API symbol can be imported."""

    def test_client_class(self):
        from clients.zewm_robco_client import ZewmRobcoClient
        assert ZewmRobcoClient is not None

    def test_exception_base(self):
        from clients.zewm_robco_exceptions import (
            RobcoError,
        )
        assert issubclass(RobcoError, Exception)
        assert callable(raise_for_error_code)

    def test_concrete_exceptions(self):
        from clients.zewm_robco_exceptions import (
            NoErrorQueueError,
            NoOrderFoundError,
            NoRobotResourceTypeError,
            QueueNotChangedError,
            RobcoInternalError,
            RobotHasOrderError,
            RobotNotFoundError,
            StatusNotSetError,
            WarehouseOrderLockedError,
            WhoAssignedError,
            WhoInProcessError,
            WhoLockedError,
            WhoNotFoundError,
            WhoNotUnassignedError,
            WhtAlreadyConfirmedError,
            WhtAssignedError,
            WhtNotConfirmedError,
        )
        assert all(issubclass(e, RobcoError) for e in (
            RobotNotFoundError,
            RobotHasOrderError,
            StatusNotSetError,
            NoRobotResourceTypeError,
            WhoNotFoundError,
            WhoLockedError,
            WhoAssignedError,
            WhoInProcessError,
            WhoNotUnassignedError,
            NoOrderFoundError,
            WarehouseOrderLockedError,
            WhtAssignedError,
            WhtNotConfirmedError,
            WhtAlreadyConfirmedError,
            NoErrorQueueError,
            QueueNotChangedError,
            RobcoInternalError,
        ))

    def test_types_module(self):
        from clients.zewm_robco_types import (
            ExceptionCode,
            RobotType,
            map_robot_error_to_exccode,
        )
        assert RobotType.MIR == "MIR"
        assert ExceptionCode.DAMAGED == "DAMG"
        assert callable(map_robot_error_to_exccode)


# ═══════════════════════════════════════════════════════════════════════
# 2. Success paths — all 8 P0/P1 methods with mocked 200 responses
# ═══════════════════════════════════════════════════════════════════════


class TestSuccessPaths:
    """Each P0/P1 method returns a parsed dict/list when SAP responds 200."""

    def test_assign_robot_who(self, client, mock_httpx):
        """P0: assign robot WHO returns assignment details."""
        sap_json = {"d": {"who": "WHO001", "rsrc": "MIR_001"}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.assign_robot_who("WH01", "MIR_001", "WHO001")
        assert result == {"who": "WHO001", "rsrc": "MIR_001"}

    def test_confirm_task_step_1(self, client, mock_httpx):
        """P0: first confirmation step returns tanum + confirmed flag."""
        sap_json = {"d": {"tanum": "TAN001", "confirmed": True}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.confirm_task_step_1("WH01", "TAN001", "MIR_001")
        assert result == {"tanum": "TAN001", "confirmed": True}

    def test_confirm_task(self, client, mock_httpx):
        """P0: full task confirmation with optional args."""
        sap_json = {"d": {"tanum": "TAN001", "nista": "PICK", "confirmed": True}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.confirm_task(
            "WH01", "TAN001", "PICK", "MIR_001",
            altme="BOX", conf_exc="DAMG",
        )
        assert result == {"tanum": "TAN001", "nista": "PICK", "confirmed": True}

    def test_unassign_robot_who(self, client, mock_httpx):
        """P0: unassign WHO returns unassigned confirmation."""
        sap_json = {"d": {"who": "WHO001", "unassigned": True}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.unassign_robot_who("WH01", "MIR_001", "WHO001")
        assert result == {"who": "WHO001", "unassigned": True}

    def test_get_new_robot_who(self, client, mock_httpx):
        """P1: get next WHO for a robot resource."""
        sap_json = {"d": {"who": "WHO042"}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.get_new_robot_who("WH01", "MIR_001")
        assert result == {"who": "WHO042"}

    def test_set_robot_status(self, client, mock_httpx):
        """P1: set robot operational status."""
        sap_json = {"d": {"rsrc": "MIR_001", "exccode": "BLKD"}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.set_robot_status("WH01", "MIR_001", "BLKD")
        assert result == {"rsrc": "MIR_001", "exccode": "BLKD"}

    def test_get_in_process_who(self, client, mock_httpx):
        """P1: list in-process WHOs returns a list of dicts."""
        sap_json = {"d": {"results": [{"Who": "W1"}, {"Who": "W2"}]}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.get_in_process_who("WH01")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_get_in_process_who_single_item(self, client, mock_httpx):
        """P1: a single result dict is wrapped into a list."""
        sap_json = {"d": {"Who": "W1"}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.get_in_process_who("WH01")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["Who"] == "W1"

    def test_get_in_process_who_empty(self, client, mock_httpx):
        """P1: empty results list returns empty list."""
        mock_httpx.request.return_value = _mock_response(200, {"d": {"results": []}})
        result = client.get_in_process_who("WH01")
        assert result == []

    def test_get_assigned_robot_who(self, client, mock_httpx):
        """P1: list WHOs assigned to a specific robot."""
        sap_json = {"d": {"results": [{"Who": "W1", "Rsrc": "MIR_001"}]}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.get_assigned_robot_who("WH01", "MIR_001")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_confirm_task_minimal_args(self, client, mock_httpx):
        """P0: confirm_task works with only required positional args."""
        sap_json = {"d": {"tanum": "TAN002", "nista": "PUT", "confirmed": True}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.confirm_task("WH01", "TAN002", "PUT", "MIR_002")
        assert result["confirmed"] is True

    def test_unassign_robot_who_unassigned_false(self, client, mock_httpx):
        """P0: unassign_robot_who can return unassigned=False."""
        sap_json = {"d": {"who": "WHO001", "unassigned": False}}
        mock_httpx.request.return_value = _mock_response(200, sap_json)
        result = client.unassign_robot_who("WH01", "MIR_001", "WHO001")
        assert result["unassigned"] is False


# ═══════════════════════════════════════════════════════════════════════
# 3. Exception mapping — 17 RobcoError subclasses for SAP error codes
# ═══════════════════════════════════════════════════════════════════════


class TestExceptionMapping:
    """Each SAP error code raises the correct typed exception."""

    _ERROR_SCENARIOS: list[tuple[str, type[RobcoError]]] = [
        ("ROBOT_NOT_FOUND",        RobotNotFoundError),
        ("ROBOT_HAS_ORDER",        RobotHasOrderError),
        ("ROBOT_STATUS_NOT_SET",   StatusNotSetError),
        ("NO_ROBOT_RESOURCE_TYPE", NoRobotResourceTypeError),
        ("WHO_NOT_FOUND",          WhoNotFoundError),
        ("WHO_LOCKED",             WhoLockedError),
        ("WHO_ASSIGNED",           WhoAssignedError),
        ("WHO_IN_PROCESS",         WhoInProcessError),
        ("WHO_NOT_UNASSIGNED",     WhoNotUnassignedError),
        ("NO_ORDER_FOUND",         NoOrderFoundError),
        ("WAREHOUSE_ORDER_LOCKED", WarehouseOrderLockedError),
        ("WHT_ASSIGNED",           WhtAssignedError),
        ("WHT_NOT_CONFIRMED",      WhtNotConfirmedError),
        ("WHT_ALREADY_CONFIRMED",  WhtAlreadyConfirmedError),
        ("NO_ERROR_QUEUE",         NoErrorQueueError),
        ("QUEUE_NOT_CHANGED",      QueueNotChangedError),
        ("INTERNAL_ERROR",         RobcoInternalError),
    ]

    @pytest.mark.parametrize("error_code,expected_cls", _ERROR_SCENARIOS)
    def test_error_raises_correct_exception(
        self, client, mock_httpx, error_code, expected_cls,
    ):
        """SAP error JSON -> corresponding RobcoError subclass."""
        sap_json = {
            "error": {
                "code": f"{error_code}/001",
                "message": {"lang": "en", "value": f"Test {error_code}"},
            },
        }
        mock_httpx.request.return_value = _mock_response(400, sap_json)
        with pytest.raises(expected_cls, match=error_code):
            client.get_new_robot_who("WH01", "R1")

    def test_internal_server_error_mapped(self, client, mock_httpx):
        """INTERNAL_SERVER_ERROR maps to RobcoInternalError."""
        sap_json = {
            "error": {
                "code": "INTERNAL_SERVER_ERROR/001",
                "message": {"lang": "en", "value": "Server error"},
            },
        }
        mock_httpx.request.return_value = _mock_response(500, sap_json)
        with pytest.raises(RobcoInternalError):
            client.get_new_robot_who("WH01", "R1")

    def test_unknown_error_code_falls_back(self, client, mock_httpx):
        """Unregistered error code raises the base RobcoError."""
        sap_json = {
            "error": {
                "code": "MYSTERY_CODE/001",
                "message": {"lang": "en", "value": "???"},
            },
        }
        mock_httpx.request.return_value = _mock_response(400, sap_json)
        with pytest.raises(RobcoError):
            client.get_new_robot_who("WH01", "R1")

    def test_non_json_error_response(self, client, mock_httpx):
        """Non-JSON error body raises RobcoInternalError with status."""
        resp = MagicMock()
        resp.status_code = 503
        resp.json.side_effect = ValueError("not JSON")
        resp.text = "Service Unavailable"
        mock_httpx.request.return_value = resp
        with pytest.raises(RobcoInternalError, match="503"):
            client.get_new_robot_who("WH01", "R1")


# ═══════════════════════════════════════════════════════════════════════
# 4. CSRF retry — 403 -> re-fetch CSRF -> retry succeeds
# ═══════════════════════════════════════════════════════════════════════


class TestCsrfRetry:
    """Client re-fetches CSRF token on 403 and retries the request."""

    def test_csrf_expiry_retry_succeeds(self, client, mock_httpx):
        """403 triggers CSRF refresh, then the request succeeds."""
        first_resp = MagicMock()
        first_resp.status_code = 403
        first_resp.text = ""

        success_resp = _mock_response(200, {"d": {"who": "RECOVERED_WHO"}})
        mock_httpx.request.side_effect = [first_resp, success_resp]

        # CSRF fetch ($metadata) response
        csrf_resp = MagicMock()
        csrf_resp.status_code = 200
        csrf_resp.headers = {"X-CSRF-Token": "fresh-csrf-token"}
        csrf_resp.cookies = []
        mock_httpx.get.return_value = csrf_resp

        result = client.get_new_robot_who("WH01", "R1")
        assert result == {"who": "RECOVERED_WHO"}
        assert mock_httpx.request.call_count == 2

    def test_csrf_retry_respects_new_token(self, client, mock_httpx):
        """After CSRF refresh, the new token is used in the retry."""
        first_resp = MagicMock()
        first_resp.status_code = 403
        first_resp.text = ""

        success_resp = _mock_response(200, {"d": {"status": "ok"}})
        mock_httpx.request.side_effect = [first_resp, success_resp]

        csrf_resp = MagicMock()
        csrf_resp.status_code = 200
        csrf_resp.headers = {"X-CSRF-Token": "refreshed-token"}
        csrf_resp.cookies = []
        mock_httpx.get.return_value = csrf_resp

        client.get_new_robot_who("WH01", "R1")

        # The second request should use the freshly fetched token
        second_call_headers = mock_httpx.request.call_args_list[1][1]["headers"]
        assert second_call_headers["X-CSRF-Token"] == "refreshed-token"


# ═══════════════════════════════════════════════════════════════════════
# 5. Rate limit — 429 -> backoff -> retry succeeds
# ═══════════════════════════════════════════════════════════════════════


class TestRateLimit:
    """Client backs off on 429 and retries the request."""

    def test_rate_limit_retry_succeeds(self, client, mock_httpx):
        """429 with Retry-After -> time.sleep -> retry -> 200."""
        with patch("time.sleep") as mock_sleep:
            limited = MagicMock()
            limited.status_code = 429
            limited.headers = {"Retry-After": "2"}
            limited.text = ""

            success = _mock_response(200, {"d": {"who": "AFTER_LIMIT"}})
            mock_httpx.request.side_effect = [limited, success]

            result = client.get_new_robot_who("WH01", "R1")
            assert result == {"who": "AFTER_LIMIT"}
            mock_sleep.assert_called_once_with(2)

    def test_rate_limit_respects_cap(self, client, mock_httpx):
        """Retry-After > 30 is capped to 30 seconds."""
        with patch("time.sleep") as mock_sleep:
            limited = MagicMock()
            limited.status_code = 429
            limited.headers = {"Retry-After": "999"}
            limited.text = ""

            success = _mock_response(200, {"d": {"who": "OK"}})
            mock_httpx.request.side_effect = [limited, success]

            client.get_new_robot_who("WH01", "R1")
            mock_sleep.assert_called_once_with(30)


# ═══════════════════════════════════════════════════════════════════════
# 6. SAP error parsing — slash-separated error codes
# ═══════════════════════════════════════════════════════════════════════


class TestSapErrorParsing:
    """Slash-suffix ``/NNN`` is stripped before dispatching."""

    def test_robot_not_found_strips_suffix(self, client, mock_httpx):
        """'ROBOT_NOT_FOUND/001' -> raises RobotNotFoundError."""
        sap_json = {
            "error": {
                "code": "ROBOT_NOT_FOUND/001",
                "message": {"lang": "en", "value": "Robot XYZ not found"},
            },
        }
        mock_httpx.request.return_value = _mock_response(404, sap_json)
        with pytest.raises(RobotNotFoundError) as exc_info:
            client.get_new_robot_who("WH01", "R1")
        assert "ROBOT_NOT_FOUND" in str(exc_info.value)

    def test_error_code_without_slash(self, client, mock_httpx):
        """Plain error code (no /NNN) is used as-is."""
        sap_json = {
            "error": {
                "code": "WHO_LOCKED",
                "message": {"lang": "en", "value": "WHO is locked"},
            },
        }
        mock_httpx.request.return_value = _mock_response(409, sap_json)
        with pytest.raises(WhoLockedError):
            client.get_new_robot_who("WH01", "R1")

    def test_malformed_error_json(self, client, mock_httpx):
        """Non-JSON response body -> RobcoInternalError with HTTP status."""
        resp = MagicMock()
        resp.status_code = 500
        resp.json.side_effect = ValueError("not JSON")
        resp.text = "Internal Server Error"
        mock_httpx.request.return_value = resp
        with pytest.raises(RobcoInternalError, match="500"):
            client.get_new_robot_who("WH01", "R1")


# ═══════════════════════════════════════════════════════════════════════
# 7. Config validation
# ═══════════════════════════════════════════════════════════════════════


class TestConfigValidation:
    """validate_config returns errors for missing fields; empty for valid."""

    def test_empty_config_returns_errors(self):
        """An empty config dict produces multiple validation errors."""
        errs = ZewmRobcoClient.validate_config({})
        assert len(errs) >= 1

    def test_missing_basic_auth_user(self):
        """Missing user for basic auth -> error."""
        errs = ZewmRobcoClient.validate_config({"base_url": "http://sap:8000", "client": "200"})
        assert any("user" in e.lower() for e in errs)

    def test_missing_basic_auth_password(self):
        """Missing both password and password_file -> error."""
        errs = ZewmRobcoClient.validate_config({
            "base_url": "http://sap:8000",
            "client": "200",
            "user": "USER",
        })
        assert any("password" in e.lower() for e in errs)

    def test_valid_config_returns_empty(self):
        """A fully configured basic-auth config produces zero errors."""
        cfg = {
            "base_url": "https://my-sap.example.com:44300",
            "client": "200",
            "user": "ROBCO_USER",
            "password": "strong_pass",
        }
        assert ZewmRobcoClient.validate_config(cfg) == []

    def test_oauth2_missing_token_url(self):
        """OAuth2 mode without token_url -> error."""
        errs = ZewmRobcoClient.validate_config({
            "auth_mode": "oauth2",
            "oauth2": {"client_id": "c", "client_secret": "s"},
        })
        assert any("token_url" in e.lower() for e in errs)

    def test_oauth2_missing_client_id(self):
        """OAuth2 mode without client_id -> error."""
        errs = ZewmRobcoClient.validate_config({
            "auth_mode": "oauth2",
            "oauth2": {"token_url": "https://sap/token", "client_secret": "s"},
        })
        assert any("client_id" in e.lower() for e in errs)

    def test_default_base_url_warning(self):
        """Default base_url triggers a validation warning."""
        errs = ZewmRobcoClient.validate_config({
            "base_url": "http://sap-ewm:8000",
            "user": "U",
            "password": "P",
        })
        assert any("base_url" in e.lower() for e in errs)


# ═══════════════════════════════════════════════════════════════════════
# 8. _parse_response — unwrap SAP OData V2 ``{"d": {...}}`` envelope
# ═══════════════════════════════════════════════════════════════════════


class TestParseResponse:
    """_parse_response unwraps the SAP OData V2 envelope."""

    def test_unwraps_d_envelope(self):
        """``{"d": {"Who": "123"}}`` -> ``{"Who": "123"}``."""
        resp = MagicMock()
        resp.json.return_value = {"d": {"Who": "123"}}
        assert ZewmRobcoClient._parse_response(resp) == {"Who": "123"}

    def test_no_d_key_passthrough(self):
        """Response without ``d`` key passes through unchanged."""
        resp = MagicMock()
        resp.json.return_value = {"Who": "123"}
        assert ZewmRobcoClient._parse_response(resp) == {"Who": "123"}

    def test_collection_results(self):
        """``{"d": {"results": [...]}}`` -> ``{"results": [...]}``."""
        resp = MagicMock()
        resp.json.return_value = {"d": {"results": [{"Who": "W1"}, {"Who": "W2"}]}}
        result = ZewmRobcoClient._parse_response(resp)
        assert "results" in result
        assert len(result["results"]) == 2

    def test_d_is_none(self):
        """``{"d": None}`` -> ``None``."""
        resp = MagicMock()
        resp.json.return_value = {"d": None}
        assert ZewmRobcoClient._parse_response(resp) is None


# ═══════════════════════════════════════════════════════════════════════
# 9. P2 stubs — all 4 raise NotImplementedError with descriptive messages
# ═══════════════════════════════════════════════════════════════════════


class TestP2Stubs:
    """Planned P2 methods raise NotImplementedError."""

    def test_get_new_robotgroup_who(self, client):
        with pytest.raises(NotImplementedError, match="P2 stub"):
            client.get_new_robotgroup_who()

    def test_unset_who_in_process(self, client):
        with pytest.raises(NotImplementedError, match="P2 stub"):
            client.unset_who_in_process()

    def test_send_conf_error(self, client):
        with pytest.raises(NotImplementedError, match="P2 stub"):
            client.send_conf_error()

    def test_move_who_to_error_queue(self, client):
        with pytest.raises(NotImplementedError, match="P2 stub"):
            client.move_who_to_error_queue()


# ═══════════════════════════════════════════════════════════════════════
# 10. map_robot_error_to_exccode — exact match, prefix fallback, no match
# ═══════════════════════════════════════════════════════════════════════


class TestMapRobotErrorToExccode:
    """map_robot_error_to_exccode maps robot error strings to SAP exception codes."""

    def test_exact_match(self):
        """Full error code matches an entry in the mapping table."""
        assert map_robot_error_to_exccode("ERR_QT_MOTOR_FAULT:E002") == ExceptionCode.BLOCKED

    def test_exact_match_platform_error(self):
        """Platform-level errors (no colon) match directly."""
        assert map_robot_error_to_exccode("ERR_SCS_TIMEOUT") == ExceptionCode.BLOCKED

    def test_prefix_fallback(self):
        """Unknown suffix but known prefix matches via prefix lookup.
        ``ERR_SCS_TIMEOUT`` is a standalone entry (no colon), so
        ``ERR_SCS_TIMEOUT:FOO`` splits to the known prefix.
        """
        assert map_robot_error_to_exccode("ERR_SCS_TIMEOUT:FOO") == ExceptionCode.BLOCKED

    def test_prefix_fallback_unknown_prefix(self):
        """Colon-separated error with no matching prefix returns None."""
        assert map_robot_error_to_exccode("CUSTOM_UNKNOWN:X001") is None

    def test_no_match(self):
        """Completely unknown error code returns None."""
        assert map_robot_error_to_exccode("UNKNOWN_ERR") is None

    def test_exact_match_damaged(self):
        """Damaged-related errors map to DAMG."""
        assert map_robot_error_to_exccode("ERR_QT_LIDAR_ANOMALY:E001") == ExceptionCode.DAMAGED
        assert map_robot_error_to_exccode("ERR_SENSOR_DEGRADED") == ExceptionCode.DAMAGED
