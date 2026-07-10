"""Message Router - Multi-channel distribution, priority, dedup, time control."""
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from .config import settings
from .models import NotificationRequest, Priority

logger = logging.getLogger(__name__)

# Priority to TTL mapping (how long to keep trying)
PRIORITY_TTL = {
    Priority.P0: 300,    # 5 minutes
    Priority.P1: 1800,   # 30 minutes
    Priority.P2: 3600,   # 1 hour
}

# Priority to channel mapping
PRIORITY_CHANNELS = {
    Priority.P0: ["wechat", "feishu", "dingtalk", "email"],
    Priority.P1: ["wechat", "feishu"],
    Priority.P2: ["email"],
}


class MessageRouter:
    """Routes messages to appropriate channels based on priority and config."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def init(self):
        redis_kwargs = {"decode_responses": True}
        if settings.REDIS_URL.startswith("rediss://") or os.getenv("REDIS_SSL", "false").lower() == "true":
            redis_kwargs["ssl"] = True
            redis_kwargs["ssl_cert_reqs"] = os.getenv("REDIS_SSL_CERT_REQS", "required")
        self._redis = aioredis.from_url(settings.REDIS_URL, **redis_kwargs)

    async def close(self):
        if self._redis:
            await self._redis.close()

    def resolve_channels(
        self, requested_channels: list[str], priority: Priority
    ) -> list[str]:
        """Determine which channels to send to.

        Logic:
        1. If specific channels requested, use those (filtered by enabled)
        2. Otherwise, use priority-based default channels
        3. Filter by enabled channels (based on config)
        """
        enabled = set(settings.enabled_channels)

        if requested_channels:
            channels = [ch for ch in requested_channels if ch in enabled]
        else:
            channels = [ch for ch in PRIORITY_CHANNELS.get(priority, []) if ch in enabled]

        if not channels:
            logger.warning(
                "[Router] No enabled channels for priority=%s, requested=%s, enabled=%s",
                priority, requested_channels, list(enabled),
            )

        return channels

    async def check_dedup(
        self, alert_id: str, content: str
    ) -> bool:
        """Check if this alert was already sent (deduplication).

        Returns True if it's a duplicate (should skip), False if new.
        """
        content_hash = hashlib.sha256(
            f"{alert_id}:{content}".encode()
        ).hexdigest()
        key = f"gateway:dedup:{content_hash}"

        inserted = await self._redis.set(key, "1", nx=True, ex=600)
        return not inserted  # If not inserted, it's a duplicate

    def check_time_control(self, priority: Priority) -> bool:
        """Check if current time allows sending for this priority.

        P0: always send (24/7)
        P1: 07:00-22:00 UTC
        P2: 09:00-18:00 UTC
        """
        if priority == Priority.P0:
            return True

        hour = datetime.now(timezone.utc).hour

        if priority == Priority.P1:
            return 7 <= hour < 22

        if priority == Priority.P2:
            return 9 <= hour < 18

        return True

    async def route(
        self, notification: NotificationRequest
    ) -> dict:
        """Route a notification to appropriate channels.

        Returns dict with routing results.
        """
        # 1. Dedup check
        is_dup = await self.check_dedup(notification.alert_id, notification.content)
        if is_dup:
            logger.info("[Router] Duplicate alert skipped: %s", notification.alert_id)
            return {
                "skipped": True,
                "reason": "duplicate",
                "channels": [],
            }

        # 2. Time control
        if not self.check_time_control(notification.priority):
            logger.info(
                "[Router] Time control blocked alert %s (priority=%s)",
                notification.alert_id, notification.priority,
            )
            return {
                "skipped": True,
                "reason": "time_control",
                "channels": [],
            }

        # 3. Resolve channels
        channels = self.resolve_channels(
            notification.channels, notification.priority
        )

        if not channels:
            return {
                "skipped": True,
                "reason": "no_enabled_channels",
                "channels": [],
            }

        return {
            "skipped": False,
            "channels": channels,
            "priority": notification.priority.value,
            "ttl": PRIORITY_TTL.get(notification.priority, 600),
        }
