"""Order data models for the robot dispatch platform."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class OrderType(str, Enum):
    PICK = "PICK"
    PUT = "PUT"
    MOVE = "MOVE"
    CHARGE = "CHARGE"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUSPENDED = "SUSPENDED"
    DIFF_SUSPENDED = "DIFF_SUSPENDED"


# Priority: 0=critical, 1=high, 2=normal, 3=low
OrderPriority = int  # 0 | 1 | 2 | 3


@dataclass
class WarehouseOrder:
    """Core order entity representing a robot dispatch task.

    Maps to the orders_v2 table in SQLite.
    """
    order_no: str
    type: OrderType = OrderType.MOVE
    priority: OrderPriority = 3
    source: Optional[str] = None          # SAP warehouse task ID
    robot_brand: Optional[str] = None
    robot_serial: Optional[str] = None
    status: OrderStatus = OrderStatus.CREATED
    payload: Optional[dict] = None        # VDA5050 order payload
    zone_id: Optional[str] = None
    location: Optional[str] = None
    weight: Optional[float] = None
    env_tag: str = "PROD"
    expected_qty: Optional[int] = None
    assigned_rule_id: Optional[int] = None
    error_message: Optional[str] = None
    id: Optional[int] = None
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = _now()
        if self.updated_at is None:
            self.updated_at = self.created_at

    def mark_assigned(self, robot_brand: str, robot_serial: str):
        """Assign order to a robot."""
        self.robot_brand = robot_brand
        self.robot_serial = robot_serial
        self.status = OrderStatus.ASSIGNED
        self.updated_at = _now()

    def mark_in_progress(self):
        """Order execution started."""
        self.status = OrderStatus.IN_PROGRESS
        self.updated_at = _now()

    def mark_completed(self):
        """Order completed successfully."""
        self.status = OrderStatus.COMPLETED
        self.completed_at = _now()
        self.updated_at = self.completed_at

    def mark_failed(self, error: str):
        """Order failed."""
        self.status = OrderStatus.FAILED
        self.error_message = error
        self.updated_at = _now()

    def mark_cancelled(self):
        """Order cancelled by operator/system."""
        self.status = OrderStatus.CANCELLED
        self.updated_at = _now()

    def mark_suspended(self, reason: str):
        """Order suspended (needs human intervention)."""
        self.status = OrderStatus.SUSPENDED
        self.error_message = reason
        self.updated_at = _now()

    def to_dict(self) -> dict:
        """Serialize to dict for JSON response / DB insert."""
        return {
            "id": self.id,
            "orderNo": self.order_no,
            "type": self.type.value,
            "priority": self.priority,
            "source": self.source,
            "robotBrand": self.robot_brand,
            "robotSerial": self.robot_serial,
            "status": self.status.value,
            "payload": self.payload,
            "zoneId": self.zone_id,
            "location": self.location,
            "weight": self.weight,
            "envTag": self.env_tag,
            "expectedQty": self.expected_qty,
            "assignedRuleId": self.assigned_rule_id,
            "errorMessage": self.error_message,
            "version": self.version,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "completedAt": self.completed_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
