"""Card Template Engine - Convert system events to platform-specific interactive cards.

Supports three platforms:
- WeChat (企业微信): template_card messages
- Feishu (飞书): interactive card messages
- DingTalk (钉钉): action_card messages
"""

import logging
import os
from typing import Any

from .models import ActionType, NotificationRequest, Priority, TargetType

logger = logging.getLogger(__name__)

# Public URL used in card action links. Must point to the gateway's webhook endpoint.
GATEWAY_PUBLIC_URL = os.getenv("GATEWAY_PUBLIC_URL", "https://ewma.example.com")


class CardTemplateEngine:
    """Generates platform-specific card payloads from system events."""

    # Priority to emoji mapping
    PRIORITY_EMOJI = {
        Priority.P0: "🚨",
        Priority.P1: "⚠️",
        Priority.P2: "📢",
    }

    # Action type to button text mapping (includes target_id for clarity)
    ACTION_BUTTON_TEXT = {
        ActionType.ROBOT_STOP: "确认急停 {target_id}",
        ActionType.ROBOT_RECALL: "确认召回 {target_id}",
        ActionType.ORDER_CANCEL: "确认取消订单 {target_id}",
        ActionType.ZONE_LOCK: "确认封锁区域 {target_id}",
        ActionType.ZONE_UNLOCK: "确认解锁区域 {target_id}",
        ActionType.DISMISS: "忽略",
        ActionType.VIEW_ORDER: "查看详情",
        ActionType.VIEW_ROBOT: "查看详情",
    }

    # Action type to danger level
    ACTION_DANGER = {
        ActionType.ROBOT_STOP: True,
        ActionType.ROBOT_RECALL: True,
        ActionType.ORDER_CANCEL: True,
        ActionType.ZONE_LOCK: True,
        ActionType.ZONE_UNLOCK: False,
        ActionType.DISMISS: False,
        ActionType.VIEW_ORDER: False,
        ActionType.VIEW_ROBOT: False,
    }

    def _get_button_text(self, action_type: ActionType, target_id: str) -> str:
        template = self.ACTION_BUTTON_TEXT.get(action_type, "确认")
        return template.format(target_id=target_id)

    def _is_dangerous(self, action_type: ActionType) -> bool:
        return self.ACTION_DANGER.get(action_type, True)

    def generate_wechat_card(self, notification: NotificationRequest) -> dict[str, Any]:
        """Generate WeChat (企业微信) template_card payload."""
        emoji = self.PRIORITY_EMOJI.get(notification.priority, "📢")
        button_text = self._get_button_text(notification.action_type, notification.target.target_id)

        card = {
            "msgtype": "template_card",
            "template_card": {
                "card_type": "text_notice",
                "source": {
                    "desc": "EWM AGV 调度平台",
                    "desc_color": 1 if notification.priority == Priority.P0 else 0,
                },
                "main_title": {
                    "title": f"{emoji} {notification.priority} 告警：{notification.title}",
                    "desc": notification.content[:200],
                },
                "emphasis_content": {
                    "title": notification.target.target_id,
                    "desc": f"目标{notification.target.target_type.value}",
                },
                "sub_title_text": notification.content,
                "card_action": {
                    "type": 1,
                    "url": f"{GATEWAY_PUBLIC_URL}/{notification.target.target_type.value}/{notification.target.target_id}",
                },
            },
        }

        # Add action buttons via subsequent message
        card["button_text"] = button_text
        card["button_action"] = {
            "action_type": notification.action_type.value,
            "target_id": notification.target.target_id,
            "target_type": notification.target.target_type.value,
            "confirm_required": notification.require_confirm,
        }

        return card

    def generate_feishu_card(self, notification: NotificationRequest) -> dict[str, Any]:
        """Generate Feishu (飞书) interactive card payload."""
        emoji = self.PRIORITY_EMOJI.get(notification.priority, "📢")
        button_text = self._get_button_text(notification.action_type, notification.target.target_id)
        is_danger = self._is_dangerous(notification.action_type)
        header_template = (
            "red" if is_danger else ("orange" if notification.priority == Priority.P1 else "blue")
        )

        # Build action buttons
        buttons = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": button_text},
                "type": "danger" if is_danger else "primary",
                "value": {
                    "action_type": notification.action_type.value,
                    "target_id": notification.target.target_id,
                    "target_type": notification.target.target_type.value,
                    "confirm_required": notification.require_confirm,
                    "correlation_id": notification.correlation_id,
                    "alert_id": notification.alert_id,
                },
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看详情"},
                "type": "default",
                "value": {
                    "action_type": "view_detail",
                    "target_id": notification.target.target_id,
                },
            },
        ]

        card = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{emoji} {notification.title}",
                    },
                    "template": header_template,
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"**优先级：** {notification.priority}\n"
                                f"**目标：** {notification.target.target_type.value} {notification.target.target_id}\n"
                                f"**详情：** {notification.content}\n"
                                f"**告警ID：** {notification.alert_id}"
                            ),
                        },
                    },
                    {"tag": "hr"},
                    {"tag": "action", "actions": buttons},
                ],
            },
        }

        return card

    def generate_dingtalk_card(self, notification: NotificationRequest) -> dict[str, Any]:
        """Generate DingTalk (钉钉) action_card payload."""
        emoji = self.PRIORITY_EMOJI.get(notification.priority, "📢")
        button_text = self._get_button_text(notification.action_type, notification.target.target_id)

        markdown = (
            f"### {emoji} {notification.title}\n\n"
            f"**优先级：** {notification.priority}\n\n"
            f"**目标：** {notification.target.target_type.value} {notification.target.target_id}\n\n"
            f"**详情：** {notification.content}\n\n"
            f"**告警ID：** {notification.alert_id}\n\n"
            f"> 点击下方按钮执行操作"
        )

        card = {
            "msgtype": "action_card",
            "action_card": {
                "title": f"{emoji} {notification.priority} 告警：{notification.title}",
                "markdown": markdown,
                "btn_orientation": "1",
                "btns": [
                    {
                        "title": button_text,
                        "action_url": (
                            f"{GATEWAY_PUBLIC_URL}/webhook/dingtalk?"
                            f"action={notification.action_type.value}"
                            f"&target={notification.target.target_id}"
                            f"&type={notification.target.target_type.value}"
                            f"&alert_id={notification.alert_id}"
                            f"&corr={notification.correlation_id}"
                        ),
                    },
                    {
                        "title": "查看详情",
                        "action_url": (
                            f"{GATEWAY_PUBLIC_URL}/{notification.target.target_type.value}/"
                            f"{notification.target.target_id}"
                        ),
                    },
                ],
            },
        }

        return card

    def generate_email_body(self, notification: NotificationRequest) -> tuple[str, str]:
        """Generate email subject and HTML body.

        Returns (subject, html_body).
        """
        emoji = self.PRIORITY_EMOJI.get(notification.priority, "📢")
        subject = f"[{notification.priority}] {notification.title}"

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: {"#dc3545" if notification.priority == Priority.P0 else "#ffc107" if notification.priority == Priority.P1 else "#17a2b8"};">
                    {emoji} {notification.title}
                </h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">优先级</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{notification.priority}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">目标类型</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{notification.target.target_type.value}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">目标ID</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{notification.target.target_id}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">告警ID</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{notification.alert_id}</td></tr>
                </table>
                <div style="padding: 16px; background: #f8f9fa; border-radius: 4px; margin: 16px 0;">
                    <p>{notification.content}</p>
                </div>
                <p style="color: #6c757d; font-size: 12px;">
                    此邮件由系统自动发送，请勿回复。如需操作，请前往 Web UI 或使用企业微信/飞书/钉钉进行确认。
                </p>
            </div>
        </body>
        </html>
        """

        return subject, html

    def generate_secondary_confirm_card(
        self,
        platform: str,
        action_type: ActionType,
        target_id: str,
        target_type: TargetType,
        confirm_token: str,
        alert_id: str,
    ) -> dict[str, Any]:
        """Generate a secondary confirmation card for dangerous operations.

        This card is sent after the first click, requiring the user to confirm again.
        """
        button_text = self._get_button_text(action_type, target_id)

        if platform == "wechat":
            return {
                "msgtype": "template_card",
                "template_card": {
                    "card_type": "text_notice",
                    "source": {"desc": "⚠️ 二次确认", "desc_color": 1},
                    "main_title": {
                        "title": "⚠️ 请确认操作",
                        "desc": f"即将执行: {button_text}",
                    },
                    "sub_title_text": (
                        f"操作类型: {action_type.value}\n"
                        f"目标: {target_type.value} {target_id}\n\n"
                        f"此操作不可撤销，请确认无误后点击确认。"
                    ),
                },
                "button_text": f"确认执行: {button_text}",
                "button_action": {
                    "action_type": action_type.value,
                    "target_id": target_id,
                    "target_type": target_type.value,
                    "confirm_token": confirm_token,
                },
            }

        elif platform == "feishu":
            return {
                "msg_type": "interactive",
                "card": {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": "⚠️ 二次确认"},
                        "template": "red",
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    f"**即将执行:** {button_text}\n\n"
                                    f"**操作类型:** {action_type.value}\n"
                                    f"**目标:** {target_type.value} {target_id}\n\n"
                                    f"⚠️ 此操作不可撤销，请确认无误后点击确认。"
                                ),
                            },
                        },
                        {
                            "tag": "action",
                            "actions": [
                                {
                                    "tag": "button",
                                    "text": {
                                        "tag": "plain_text",
                                        "content": f"确认执行: {button_text}",
                                    },
                                    "type": "danger",
                                    "value": {
                                        "action_type": action_type.value,
                                        "target_id": target_id,
                                        "target_type": target_type.value,
                                        "confirm_token": confirm_token,
                                        "alert_id": alert_id,
                                    },
                                },
                                {
                                    "tag": "button",
                                    "text": {"tag": "plain_text", "content": "取消"},
                                    "type": "default",
                                    "value": {
                                        "action_type": "dismiss",
                                    },
                                },
                            ],
                        },
                    ],
                },
            }

        elif platform == "dingtalk":
            return {
                "msgtype": "action_card",
                "action_card": {
                    "title": "⚠️ 二次确认",
                    "markdown": (
                        f"### ⚠️ 请确认操作\n\n"
                        f"**即将执行:** {button_text}\n\n"
                        f"**操作类型:** {action_type.value}\n"
                        f"**目标:** {target_type.value} {target_id}\n\n"
                        f"> ⚠️ 此操作不可撤销，请确认无误后点击确认。"
                    ),
                    "btn_orientation": "1",
                    "btns": [
                        {
                            "title": f"确认执行: {button_text}",
                            "action_url": (
                                f"{GATEWAY_PUBLIC_URL}/webhook/dingtalk?"
                                f"action={action_type.value}&target={target_id}"
                                f"&type={target_type.value}&token={confirm_token}"
                                f"&alert_id={alert_id}"
                            ),
                        },
                        {
                            "title": "取消",
                            "action_url": f"{GATEWAY_PUBLIC_URL}/webhook/dingtalk?action=dismiss",
                        },
                    ],
                },
            }

        return {}
