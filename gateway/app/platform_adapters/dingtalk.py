"""DingTalk (钉钉) platform adapter."""
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Optional

import httpx

from ..config import settings
from ..models import PlatformCallback

logger = logging.getLogger(__name__)


class DingTalkAdapter:
    """Handles DingTalk (钉钉) message sending and callback verification."""

    BASE_URL = "https://oapi.dingtalk.com"
    TOKEN_URL = f"{BASE_URL}/gettoken"
    MESSAGE_URL = f"{BASE_URL}/topapi/message/corpconversation/asyncsend_v2"

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
        """Fetch and cache access token with HTTP/JSON error handling."""
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        try:
            resp = await self._http.get(
                self.TOKEN_URL,
                params={
                    "appkey": settings.DINGTALK_APP_KEY,
                    "appsecret": settings.DINGTALK_APP_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error("[DingTalk] Token request failed: %s", e)
            return ""

        if data.get("errcode") != 0:
            logger.error("[DingTalk] Failed to get access token: %s", data)
            return ""

        self._access_token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 7200)
        return self._access_token

    async def send_message(
        self, card_payload: dict, recipients: list[str]
    ) -> dict:
        """Send an action_card message to specified users."""
        token = await self._get_access_token()
        if not token:
            return {"status": "failed", "message_id": None, "error": "no access token"}

        action_card = card_payload.get("action_card", {})
        payload = {
            "agent_id": settings.DINGTALK_ROBOT_CODE,
            "userid_list": ",".join(recipients),
            "msg": {
                "msgtype": "action_card",
                "action_card": {
                    "title": action_card.get("title", ""),
                    "markdown": action_card.get("markdown", ""),
                    "btn_orientation": action_card.get("btn_orientation", "1"),
                    "btns": action_card.get("btns", []),
                },
            },
        }

        try:
            resp = await self._http.post(
                self.MESSAGE_URL,
                params={"access_token": token},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") == 0:
                task_id = str(data.get("task_id", ""))
                logger.info("[DingTalk] Sent to %s, task_id=%s", recipients, task_id)
                return {"status": "sent", "message_id": task_id}
            else:
                logger.error("[DingTalk] Send failed: %s", data)
                return {"status": "failed", "message_id": None, "error": str(data)}
        except httpx.HTTPError as e:
            logger.error("[DingTalk] HTTP error: %s", e)
            return {"status": "failed", "message_id": None, "error": str(e)}
        except json.JSONDecodeError as e:
            logger.error("[DingTalk] Non-JSON response: %s", e)
            return {"status": "failed", "message_id": None, "error": "non_json_response"}

    def verify_sign(
        self, timestamp: str, sign: str, secret: str = ""
    ) -> bool:
        """Verify DingTalk callback signature (HMAC-SHA256).

        DingTalk uses HMAC-SHA256 with the robot's signing secret.
        """
        verify_secret = secret or settings.DINGTALK_SIGN_SECRET
        if not verify_secret:
            logger.error("[DingTalk] No sign secret configured")
            return False

        string_to_sign = f"{timestamp}\n{verify_secret}"
        hmac_code = hmac.new(
            verify_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256,
        ).digest()
        computed = base64.b64encode(hmac_code).decode()

        return hmac.compare_digest(computed, sign)

    def parse_callback(self, body: dict) -> Optional[PlatformCallback]:
        """Parse DingTalk callback into unified format."""
        try:
            # DingTalk action card callback
            action_url = body.get("action_url", "")
            # Parse action from URL query params
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(action_url)
            params = parse_qs(parsed.query)

            action_type = params.get("action", ["dismiss"])[0]
            target_id = params.get("target", [""])[0]
            target_type = params.get("type", ["robot"])[0]
            alert_id = params.get("alert_id", [""])[0]
            correlation_id = params.get("corr", [""])[0]
            confirm_token = params.get("token", [""])[0]

            action_params = {}
            if confirm_token:
                action_params["confirm_token"] = confirm_token

            return PlatformCallback(
                event_id=body.get("event_id", ""),
                platform="dingtalk",
                message_id=body.get("msg_id", ""),
                timestamp=body.get("create_at", 0),
                user={
                    "platform_user_id": body.get("sender_id", ""),
                    "platform_user_name": body.get("sender_nick", ""),
                    "bound_user_id": None,
                },
                action={
                    "action_type": action_type,
                    "target_id": target_id,
                    "target_type": target_type,
                    "params": action_params,
                },
                card_context={
                    "original_alert_id": alert_id,
                    "correlation_id": correlation_id,
                },
            )
        except Exception as e:
            logger.error("[DingTalk] Failed to parse callback: %s", e)

        return None
