"""WeChat (企业微信) platform adapter."""
import hashlib
import logging
from typing import Any, Optional

import httpx

from ..config import settings
from ..models import PlatformCallback

logger = logging.getLogger(__name__)


class WeChatAdapter:
    """Handles WeChat Work (企业微信) message sending and callback verification."""

    BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin"
    TOKEN_URL = f"{BASE_URL}/gettoken"
    MESSAGE_URL = f"{BASE_URL}/message/send"

    def __init__(self):
        self._http: Optional[httpx.AsyncClient] = None
        self._access_token: str = ""
        self._token_expires: int = 0

    async def init(self):
        self._http = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        if self._http:
            await self._http.aclose()

    async def _get_access_token(self) -> str:
        """Fetch and cache access token."""
        import time
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        resp = await self._http.get(
            self.TOKEN_URL,
            params={
                "corpid": settings.WECOM_CORP_ID,
                "corpsecret": settings.WECOM_SECRET,
            },
        )
        data = resp.json()
        if data.get("errcode") != 0:
            logger.error("[WeChat] Failed to get access token: %s", data)
            return ""

        self._access_token = data["access_token"]
        self._token_expires = int(time.time()) + data.get("expires_in", 7200)
        return self._access_token

    async def send_message(
        self, card_payload: dict, recipients: list[str]
    ) -> dict:
        """Send a card message to specified users."""
        token = await self._get_access_token()
        if not token:
            return {"status": "failed", "message_id": None, "error": "no access token"}

        # WeChat sends to users by user_id or mobile
        touser = "|".join(recipients) if recipients else "@all"

        payload = {
            "touser": touser,
            "msgtype": card_payload.get("msgtype", "template_card"),
            "agentid": settings.WECOM_AGENT_ID,
            card_payload.get("msgtype", "template_card"): card_payload.get(
                "template_card", {}
            ),
        }

        try:
            resp = await self._http.post(
                self.MESSAGE_URL,
                params={"access_token": token},
                json=payload,
            )
            data = resp.json()
            if data.get("errcode") == 0:
                msg_id = data.get("msgid", "")
                logger.info("[WeChat] Sent to %s, msgid=%s", recipients, msg_id)
                return {"status": "sent", "message_id": msg_id}
            else:
                logger.error("[WeChat] Send failed: %s", data)
                return {"status": "failed", "message_id": None, "error": str(data)}
        except httpx.RequestError as e:
            logger.error("[WeChat] Request error: %s", e)
            return {"status": "failed", "message_id": None, "error": str(e)}

    def verify_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        echostr: str = "",
        token: str = "",
    ) -> bool:
        """Verify WeChat callback signature.

        WeChat uses SHA1(sorted([token, timestamp, nonce])) for URL verification.
        """
        verify_token = token or settings.WECOM_TOKEN
        if not verify_token:
            logger.error("[WeChat] No token configured for signature verification")
            return False

        parts = sorted([verify_token, timestamp, nonce])
        computed = hashlib.sha1("".join(parts).encode()).hexdigest()

        if computed == signature:
            return True

        logger.warning(
            "[WeChat] Signature mismatch: expected=%s, got=%s", computed, signature
        )
        return False

    def parse_callback(self, raw_body: dict) -> Optional[PlatformCallback]:
        """Parse WeChat callback into unified format."""
        try:
            event_type = raw_body.get("EventType", "")
            if event_type == "template_card_event":
                task_id = raw_body.get("TaskId", "")
                button_key = raw_body.get("TaskId", "")
                # The button value contains the action data
                selected_items = raw_body.get("SelectedItems", [])
                if selected_items:
                    item = selected_items[0]
                    value = item.get("Value", {})
                else:
                    value = raw_body.get("Value", {})

                return PlatformCallback(
                    event_id=raw_body.get("TaskId", ""),
                    platform="wechat",
                    message_id=task_id,
                    timestamp=raw_body.get("CreateTime", 0),
                    user={
                        "platform_user_id": raw_body.get("FromUserName", ""),
                        "platform_user_name": raw_body.get("FromUserName", ""),
                        "bound_user_id": None,
                    },
                    action={
                        "action_type": value.get("action_type", "dismiss"),
                        "target_id": value.get("target_id", ""),
                        "target_type": value.get("target_type", "robot"),
                        "params": value.get("params", {}),
                    },
                    card_context={
                        "original_alert_id": value.get("alert_id", ""),
                        "correlation_id": value.get("correlation_id", ""),
                    },
                )
        except Exception as e:
            logger.error("[WeChat] Failed to parse callback: %s", e)

        return None
