"""Tests for the Card Template Engine."""
import pytest

from gateway.app.card_template_engine import CardTemplateEngine
from gateway.app.models import (
    ActionType, ConfirmType, NotificationRequest,
    Priority, Target, TargetType,
)


@pytest.fixture
def engine():
    return CardTemplateEngine()


@pytest.fixture
def p0_notification():
    return NotificationRequest(
        alert_id="ALT_001",
        priority=Priority.P0,
        title="机器人路径冲突告警",
        content="机器人 R-01 在 Zone-A 与 R-02 路径冲突",
        action_type=ActionType.ROBOT_STOP,
        target=Target(target_type=TargetType.ROBOT, target_id="R-01"),
        channels=["wechat", "feishu", "dingtalk"],
        recipients=["USER_10086"],
        require_confirm=True,
        confirm_type=ConfirmType.SECONDARY,
        correlation_id="corr_001",
    )


def test_wechat_card_has_target_id_in_button(engine, p0_notification):
    """WeChat card button text must include target ID."""
    card = engine.generate_wechat_card(p0_notification)
    assert "R-01" in card["button_text"]
    assert card["button_action"]["action_type"] == "robot_stop"
    assert card["button_action"]["target_id"] == "R-01"


def test_feishu_card_has_danger_button(engine, p0_notification):
    """Feishu card should have danger button for P0 robot_stop."""
    card = engine.generate_feishu_card(p0_notification)
    assert card["msg_type"] == "interactive"

    actions = card["card"]["elements"]
    action_element = [e for e in actions if e.get("tag") == "action"][0]
    buttons = action_element["actions"]

    assert buttons[0]["type"] == "danger"  # P0 robot_stop is dangerous
    assert "R-01" in buttons[0]["text"]["content"]
    assert buttons[0]["value"]["action_type"] == "robot_stop"


def test_dingtalk_card_has_action_url(engine, p0_notification):
    """DingTalk card should have action_url with target_id in query params."""
    card = engine.generate_dingtalk_card(p0_notification)
    assert card["msgtype"] == "action_card"

    btns = card["action_card"]["btns"]
    assert len(btns) >= 1
    assert "R-01" in btns[0]["action_url"]
    assert "robot_stop" in btns[0]["action_url"]


def test_email_body_has_subject_and_html(engine, p0_notification):
    """Email should have subject and HTML body."""
    subject, html = engine.generate_email_body(p0_notification)
    assert "P0" in subject
    assert "R-01" in html
    assert "<html>" in html


def test_secondary_confirm_card_feishu(engine):
    """Secondary confirmation card for Feishu should have confirm and cancel buttons."""
    card = engine.generate_secondary_confirm_card(
        platform="feishu",
        action_type=ActionType.ROBOT_STOP,
        target_id="R-01",
        target_type=TargetType.ROBOT,
        confirm_token="tkn_test123",
        alert_id="ALT_001",
    )

    assert card["msg_type"] == "interactive"
    actions = card["card"]["elements"]
    action_element = [e for e in actions if e.get("tag") == "action"][0]
    buttons = action_element["actions"]

    assert len(buttons) == 2  # confirm + cancel
    assert buttons[0]["type"] == "danger"  # confirm button is danger
    assert buttons[0]["value"]["confirm_token"] == "tkn_test123"
    assert buttons[1]["value"]["action_type"] == "dismiss"
