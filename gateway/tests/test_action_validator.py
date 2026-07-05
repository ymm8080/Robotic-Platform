"""Tests for the Action Validator six-layer validation."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.app.action_validator import ActionValidator, ValidationResult
from gateway.app.models import ActionType, CallbackAction, TargetType


@pytest.fixture
def validator():
    v = ActionValidator()
    v._redis = AsyncMock()
    v._http = AsyncMock()
    return v


@pytest.fixture
def action():
    return CallbackAction(
        action_type=ActionType.ROBOT_STOP,
        target_id="R-01",
        target_type=TargetType.ROBOT,
        params={},
    )


@pytest.fixture
def card_context():
    return {"original_alert_id": "ALT_001", "correlation_id": "corr_001"}


# -- Layer 1: Identity --

@pytest.mark.asyncio
async def test_identity_unbound_user_rejected(validator, action, card_context):
    """Unbound platform users must be rejected at Layer 1."""
    validator._redis.get = AsyncMock(return_value=None)

    results = await validator.validate("wechat", "unbound_user", action, card_context)

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].layer == "identity"


@pytest.mark.asyncio
async def test_identity_bound_user_passes(validator, action, card_context):
    """Bound platform users pass Layer 1."""
    validator._redis.get = AsyncMock(side_effect=[
        "USER_10086",  # identity lookup
        None,  # permission (will fail, but we're testing identity)
    ])

    results = await validator.validate("wechat", "bound_user", action, card_context)

    assert results[0].passed is True
    assert results[0].layer == "identity"
    assert results[0].detail["bound_user_id"] == "USER_10086"


# -- Layer 2: Permission --

@pytest.mark.asyncio
async def test_permission_no_permissions_rejected(validator, action, card_context):
    """User with no permissions must be rejected at Layer 2."""
    validator._redis.get = AsyncMock(side_effect=[
        "USER_10086",  # identity
    ])
    validator._redis.smembers = AsyncMock(return_value=set())

    results = await validator.validate("wechat", "user1", action, card_context)

    failed = [r for r in results if not r.passed]
    assert len(failed) > 0
    assert failed[0].layer == "permission"


@pytest.mark.asyncio
async def test_permission_has_permission_passes(validator, action, card_context):
    """User with correct permission passes Layer 2."""
    validator._redis.get = AsyncMock(side_effect=[
        "USER_10086",  # identity
    ])
    validator._redis.smembers = AsyncMock(return_value={"robot_stop", "order_cancel"})
    validator._redis.set = AsyncMock(return_value=True)  # anti-replay

    # Mock HTTP for object validation
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"state": "EXECUTING"}
    validator._http.get = AsyncMock(return_value=mock_resp)

    # Mock for pre-execution (safe mode check)
    validator._redis.get = AsyncMock(side_effect=[
        "USER_10086",  # identity
        None,  # safe mode check (not in safe mode)
        None,  # estop check
    ])

    results = await validator.validate("wechat", "user1", action, card_context)

    # Should pass all layers for non-dangerous path (but robot_stop is dangerous)
    # So it will hit Layer 5 (secondary confirmation) which will fail (no token)
    layer5 = [r for r in results if r.layer == "secondary_confirm"]
    assert len(layer5) == 1
    assert layer5[0].passed is False  # needs confirm token
    assert layer5[0].detail.get("need_confirm") is True


# -- Layer 4: Anti-replay --

@pytest.mark.asyncio
async def test_anti_replay_duplicate_rejected(validator, action, card_context):
    """Duplicate operations must be rejected at Layer 4."""
    validator._redis.get = AsyncMock(side_effect=[
        "USER_10086",  # identity
    ])
    validator._redis.smembers = AsyncMock(return_value={"robot_stop"})
    validator._redis.set = AsyncMock(return_value=False)  # already exists = duplicate

    results = await validator.validate("wechat", "user1", action, card_context)

    failed = [r for r in results if not r.passed]
    assert len(failed) > 0
    assert failed[0].layer == "anti_replay"


# -- Layer 5: Secondary confirmation --

@pytest.mark.asyncio
async def test_dangerous_action_requires_confirm(validator, action, card_context):
    """Dangerous actions without confirm_token should request confirmation."""
    validator._redis.get = AsyncMock(side_effect=[
        "USER_10086",  # identity
    ])
    validator._redis.smembers = AsyncMock(return_value={"robot_stop"})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"state": "EXECUTING"}
    validator._http.get = AsyncMock(return_value=mock_resp)

    validator._redis.set = AsyncMock(return_value=True)  # anti-replay passes
    validator._redis.hset = AsyncMock(return_value=True)
    validator._redis.expire = AsyncMock(return_value=True)

    results = await validator.validate("wechat", "user1", action, card_context)

    layer5 = [r for r in results if r.layer == "secondary_confirm"]
    assert len(layer5) == 1
    assert layer5[0].passed is False
    assert "confirm_token" in layer5[0].detail
    assert layer5[0].detail["need_confirm"] is True


@pytest.mark.asyncio
async def test_readonly_action_no_confirm_needed():
    """Read-only actions should not require secondary confirmation."""
    v = ActionValidator()
    v._redis = AsyncMock()
    v._http = AsyncMock()

    readonly_action = CallbackAction(
        action_type=ActionType.DISMISS,
        target_id="",
        target_type=TargetType.ROBOT,
        params={},
    )

    v._redis.get = AsyncMock(side_effect=[
        "USER_10086",  # identity
        None,  # safe mode (Layer 6)
    ])

    results = await v.validate("wechat", "user1", readonly_action, {"original_alert_id": "ALT_001", "correlation_id": "corr_001"})

    # DISMISS is readonly, should skip permission check
    perm_layer = [r for r in results if r.layer == "permission"]
    assert perm_layer[0].passed is True

    # No secondary confirm needed for readonly
    confirm_layer = [r for r in results if r.layer == "secondary_confirm"]
    assert confirm_layer[0].passed is True
