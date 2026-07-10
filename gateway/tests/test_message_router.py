"""Tests for the Message Router."""
import pytest
from unittest.mock import AsyncMock, patch

from gateway.app.message_router import MessageRouter
from gateway.app.models import NotificationRequest, Priority, ActionType, Target, TargetType


@pytest.fixture
def router():
    r = MessageRouter()
    r._redis = AsyncMock()
    return r


def test_resolve_channels_with_specific_request(router):
    """Specific channel requests should filter by enabled."""
    # Mock settings
    import gateway.app.config as config
    original = config.settings.enabled_channels
    config.settings.__class__.enabled_channels = property(lambda self: ["wechat", "feishu"])

    channels = router.resolve_channels(["wechat", "dingtalk"], Priority.P0)
    assert "wechat" in channels
    assert "dingtalk" not in channels  # not enabled

    config.settings.__class__.enabled_channels = original


def test_resolve_channels_priority_default(router):
    """Without specific channels, use priority-based defaults."""
    import gateway.app.config as config
    original = config.settings.enabled_channels
    config.settings.__class__.enabled_channels = property(
        lambda self: ["wechat", "feishu", "dingtalk", "email"]
    )

    channels = router.resolve_channels([], Priority.P0)
    assert len(channels) == 4  # P0 = all channels

    channels = router.resolve_channels([], Priority.P1)
    assert "wechat" in channels
    assert "feishu" in channels
    assert "email" not in channels  # P1 doesn't include email

    config.settings.__class__.enabled_channels = original


def test_check_time_control_p0_always(router):
    """P0 alerts should always pass time control."""
    assert router.check_time_control(Priority.P0) is True


@pytest.mark.asyncio
async def test_route_dedup_skips_duplicate(router):
    """Duplicate alerts should be skipped."""
    router._redis.set = AsyncMock(return_value=False)  # already exists = dup

    notification = NotificationRequest(
        alert_id="ALT_001",
        priority=Priority.P0,
        title="Test",
        content="Test content",
        action_type=ActionType.ROBOT_STOP,
        target=Target(target_type=TargetType.ROBOT, target_id="R-01"),
        channels=[],
        recipients=["user1"],
        require_confirm=False,
        correlation_id="corr_001",
    )

    result = await router.route(notification)
    assert result["skipped"] is True
    assert result["reason"] == "duplicate"
