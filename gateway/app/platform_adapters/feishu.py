"""Feishu (飞书) platform adapter."""
import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from ..config import settings
from ..models import PlatformCallback

logger = logging.getLogger(__name__)


class FeishuAdapter:
    """Handles Feishu (飞书) message sending and callback verification."""

    BASE_URL = "https://open.feishu.cn/open-apis"
    TOKEN_URL = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    MESSAGE_URL = f"{BASE_URL}/im/v1/messages"

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
        """Fetch and cache tenant access token."""
        import time
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        resp = await self._http.post(
            self.TOKEN_URL,
            json={
                "app_id": settings.FEISHU_APP_ID,
                "app_secret": settings.FEISHU_APP_SECRET,
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.error("[Feishu] Failed to get access token: %s", data)
            return ""

        self._access_token = data["tenant_access_token"]
        self._token_expires = int(time.time()) + data.get("expire", 7200)
        return self._access_token

    async def send_message(
        self, card_payload: dict, recipients: list[str]
    ) -> dict:
        """Send an interactive card to specified users."""
        token = await self._get_access_token()
        if not token:
            return {"status": "failed", "message_id": None, "error": "no access token"}

        import json
        results = []
        for recipient in recipients:
            payload = {
                "receive_id": recipient,
                "msg_type": "interactive",
                "content": json.dumps(card_payload.get("card", card_payload)),
            }
            try:
                resp = await self._http.post(
                    self.MESSAGE_URL,
                    params={"receive_id_type": "open_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
                data = resp.json()
                if data.get("code") == 0:
                    msg_id = data.get("data", {}).get("message_id", "")
                    results.append({"status": "sent", "message_id": msg_id})
                    logger.info("[Feishu] Sent to %s, msgid=%s", recipient, msg_id)
                else:
                    results.append({"status": "failed", "error": str(data)})
                    logger.error("[Feishu] Send failed for %s: %s", recipient, data)
            except httpx.RequestError as e:
                results.append({"status": "failed", "error": str(e)})
                logger.error("[Feishu] Request error: %s", e)

        # Return first result (or aggregate)
        if results and all(r.get("status") == "sent" for r in results):
            return {"status": "sent", "message_id": results[0].get("message_id")}
        elif results:
            return {"status": "partial", "message_id": results[0].get("message_id"), "detail": results}
        return {"status": "failed", "message_id": None, "error": "no results"}

    def verify_challenge(self, body: dict) -> Optional[dict]:
        """Handle Feishu URL verification challenge.

        Feishu sends a challenge request when setting up event subscription.
        Returns the challenge response if this is a verification request.
        """
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge", "")}
        return None

    def verify_token(self, token: str) -> bool:
        """Verify Feishu event verification token."""
        if not settings.FEISHU_VERIFICATION_TOKEN:
            logger.error("[Feishu] No verification token configured")
            return False
        return token == settings.FEISHU_VERIFICATION_TOKEN

    def parse_callback(self, body: dict) -> Optional[PlatformCallback]:
        """Parse Feishu callback into unified format."""
        try:
            # Handle encryption if encrypt_key is set
            event = body.get("event", body)

            # Card action callback
            if "action" in event:
                action_data = event["action"].get("value", {})
                operator = event.get("operator", {})

                return PlatformCallback(
                    event_id=event.get("uuid", ""),
                    platform="feishu",
                    message_id=event.get("open_message_id", ""),
                    timestamp=int(event.get("timestamp", 0)),
                    user={
                        "platform_user_id": operator.get("open_id", ""),
                        "platform_user_name": operator.get("name", ""),
                        "bound_user_id": None,
                    },
                    action={
                        "action_type": action_data.get("action_type", "dismiss"),
                        "target_id": action_data.get("target_id", ""),
                        "target_type": action_data.get("target_type", "robot"),
                        "params": action_data.get("params", {}),
                    },
                    card_context={
                        "original_alert_id": action_data.get("alert_id", ""),
                        "correlation_id": action_data.get("correlation_id", ""),
                    },
                )
        except Exception as e:
            logger.error("[Feishu] Failed to parse callback: %s", e)

        return None
