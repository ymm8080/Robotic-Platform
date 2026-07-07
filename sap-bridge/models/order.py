"""Order data models for the robot dispatch platform."""
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class OrderType(StrEnum):
    PICK = "PICK"
    PUT = "PUT"
    MOVE = "MOVE"
    CHARGE = "CHARGE"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUSPENDED = "SUSPENDED"
    DIFF_SUSPENDED = "DIFF_SUSPENDED"
    SAP_PENDING = "SAP_PENDING"      # COMPLETED on platform, awaiting SAP confirmation
    SAP_CONFIRMED = "SAP_CONFIRMED"  # Fully confirmed in SAP EWM/WM


# Priority: 0=critical, 1=high, 2=normal, 3=low
OrderPriority = int  # 0 | 1 | 2 | 3


@dataclass
class WarehouseOrder:
    """Core order entity representing a robot dispatch task.

    Maps to the orders table in PostgreSQL.
    """
    order_no: str
    type: OrderType = OrderType.MOVE
    priority: OrderPriority = 3
    source: str | None = None          # SAP warehouse task ID
    robot_brand: str | None = None
    robot_serial: str | None = None
    status: OrderStatus = OrderStatus.CREATED
    payload: dict | None = None        # VDA5050 order payload
    zone_id: str | None = None
    location: str | None = None
    weight: float | None = None
    env_tag: str = "PROD"
    expected_qty: int | None = None
    assigned_rule_id: int | None = None
    error_message: str | None = None
    id: int | None = None
    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None

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

    def mark_resumed(self):
        """Resume order from SUSPENDED back to IN_PROGRESS."""
        self.status = OrderStatus.IN_PROGRESS
        self.error_message = None
        self.updated_at = _now()

    def mark_sap_pending(self):
        """Order completed on platform, awaiting SAP confirmation."""
        self.status = OrderStatus.SAP_PENDING
        self.updated_at = _now()

    def mark_sap_confirmed(self):
        """SAP confirmed the warehouse task."""
        self.status = OrderStatus.SAP_CONFIRMED
        self.completed_at = _now()
        self.updated_at = self.completed_at

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
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
