"""Pydantic models for message gateway API."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class ActionType(StrEnum):
    ROBOT_STOP = "robot_stop"
    ROBOT_RECALL = "robot_recall"
    ORDER_CANCEL = "order_cancel"
    ZONE_LOCK = "zone_lock"
    ZONE_UNLOCK = "zone_unlock"
    DISMISS = "dismiss"
    VIEW_ORDER = "view_order"
    VIEW_ROBOT = "view_robot"


class TargetType(StrEnum):
    ROBOT = "robot"
    ORDER = "order"
    ZONE = "zone"


class ConfirmType(StrEnum):
    NONE = "none"
    SECONDARY = "secondary"


class OperationStatus(StrEnum):
    INIT = "INIT"
    NOTIFIED = "NOTIFIED"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class Target(BaseModel):
    target_type: TargetType
    target_id: str


class NotificationRequest(BaseModel):
    """Request body for POST /api/v1/notifications/send."""

    alert_id: str = Field(..., description="Unique alert identifier")
    priority: Priority = Field(..., description="Alert priority level")
    title: str = Field(..., description="Alert title")
    content: str = Field(..., description="Alert content body")
    action_type: ActionType = Field(..., description="Action type for button")
    target: Target = Field(..., description="Operation target")
    channels: list[str] = Field(default_factory=list, description="Notification channels")
    recipients: list[str] = Field(default_factory=list, description="Recipient user IDs")
    require_confirm: bool = Field(default=False, description="Whether confirmation is required")
    confirm_type: ConfirmType = Field(default=ConfirmType.NONE, description="Confirmation type")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    expire_at: str | None = Field(None, description="Expiration timestamp ISO format")


class ChannelResult(BaseModel):
    channel: str
    status: str
    message_id: str | None = None
    error: str | None = None


class NotificationResponse(BaseModel):
    """Response for POST /api/v1/notifications/send."""

    code: int = 0
    message: str = "发送成功"
    data: dict = Field(default_factory=dict)


class CallbackUser(BaseModel):
    platform_user_id: str
    platform_user_name: str = ""
    bound_user_id: str | None = None


class CallbackAction(BaseModel):
    action_type: ActionType
    target_id: str
    target_type: TargetType
    params: dict = Field(default_factory=dict)


class CardContext(BaseModel):
    original_alert_id: str
    correlation_id: str


class PlatformCallback(BaseModel):
    """Unified callback request from platforms."""

    event_id: str
    platform: str
    message_id: str
    timestamp: int
    user: CallbackUser
    action: CallbackAction
    card_context: CardContext


class CallbackResponse(BaseModel):
    """Response to platform callback."""

    code: int = 0
    message: str = "操作已受理"
    data: dict = Field(default_factory=dict)


class OperationResult(BaseModel):
    """Operation status query result."""

    execution_id: str
    status: OperationStatus
    action_type: str
    target_id: str
    operator: str
    operator_name: str = ""
    platform: str = ""
    created_at: str
    confirmed_at: str | None = None
    executed_at: str | None = None
    result: dict | None = None


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    log_id: str
    timestamp: str
    operator: str
    operator_name: str = ""
    platform: str
    action_type: str
    target_id: str
    target_type: str
    execution_id: str = ""
    status: str
    detail: dict = Field(default_factory=dict)
    ip_address: str = ""
    user_agent: str = ""


def utc_now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()
