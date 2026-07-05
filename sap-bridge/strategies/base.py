"""
Base robot strategy providing default VDA5050 behavior.
All brand-specific strategies inherit from this class.

v4.1: Added dispatch() method for strategy-pattern order routing.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Minimum VDA5050 version required (v4.1 verification matrix item 3)
MIN_VDA5050_VERSION = "1.1.0"


@dataclass
class DispatchResult:
    """Result of dispatching an order to a robot via brand strategy."""
    success: bool
    order_id: str
    protocol: str = "vda5050"  # vda5050 | iop | haiq | rest
    payload: dict | None = None
    error: str | None = None


@dataclass
class BatteryInfo:
    """Normalized battery state."""
    percent: float
    voltage: float | None = None
    health: float | None = None
    charging: bool = False


@dataclass
class RobotState:
    """Normalized robot state (brand-agnostic)."""
    status: str          # IDLE, MOVING, EXECUTING, CHARGING, ERROR, UNAVAILABLE
    battery: BatteryInfo
    position: dict       # {x, y, theta, lastNodeId}
    errors: list = field(default_factory=list)
    order_id: str | None = None
    operating_mode: str = "AUTOMATIC"
    driving: bool = False
    paused: bool = False
    load: Any | None = None
    raw: dict | None = None  # Original payload for debugging


@dataclass
class BrandQuirk:
    """Documented brand-specific behavior deviation."""
    name: str
    description: str
    severity: str = "INFO"  # INFO, WARN, BLOCKER


class BaseStrategy(ABC):
    """Abstract base strategy for all robot brands.

    Each brand must implement:
    - brand: Brand identifier string
    - supported_versions: List of VDA5050 versions
    - handle_state(): Map raw VDA5050 state → normalized RobotState
    - normalize_battery(): Brand-specific battery conversion
    - get_quirks(): Documented quirks list
    """

    @property
    @abstractmethod
    def brand(self) -> str:
        """Brand identifier (e.g., 'KUKA', 'MiR', 'OTTO')."""
        ...

    @property
    @abstractmethod
    def supported_versions(self) -> list[str]:
        """Supported VDA5050 versions."""
        ...

    @abstractmethod
    def handle_state(self, state: dict) -> RobotState:
        """Map raw VDA5050 state message to normalized RobotState."""
        ...

    @abstractmethod
    def normalize_battery(self, raw: Any) -> BatteryInfo:
        """Convert brand-specific battery format to normalized BatteryInfo."""
        ...

    @abstractmethod
    def dispatch(self, order: dict) -> DispatchResult:
        """Build brand-specific dispatch payload for an order.

        Args:
            order: Order dict with keys: orderId, serialNumber, nodes, edges, etc.

        Returns:
            DispatchResult with the VDA5050 (or proprietary) payload.
        """
        ...

    def check_version_compatibility(self, version: str = MIN_VDA5050_VERSION) -> bool:
        """Check if this strategy supports the minimum required VDA5050 version.

        v4.1 verification matrix item 3: All brands must support >= v1.1.0.
        """
        return any(
            _compare_versions(supported, version) >= 0
            for supported in self.supported_versions
        )

    def get_quirks(self) -> list[BrandQuirk]:
        """Return documented brand quirks. Override in subclasses."""
        return []

    # ── Common helpers ──────────────────────────────────────────

    def map_connection_state(self, raw: dict) -> str:
        """Map VDA5050 connectionState to internal status."""
        mapping = {
            "ONLINE": "ONLINE",
            "OFFLINE": "OFFLINE",
            "CONNECTIONBROKEN": "OFFLINE",
        }
        return mapping.get(raw.get("connectionState", ""), "UNKNOWN")

    def map_operating_mode(self, raw: str) -> str:
        """Normalize operating mode string."""
        if raw.upper() in ("AUTOMATIC", "SEMIAUTOMATIC"):
            return raw.upper()
        return "MANUAL"

    def validate_state_transition(self, from_state: str, to_state: str) -> bool:
        """Validate VDA5050 state transition rules."""
        allowed = {
            "INIT": ["IDLE", "ERROR"],
            "IDLE": ["MOVING", "CHARGING", "ERROR", "UNAVAILABLE"],
            "MOVING": ["IDLE", "EXECUTING", "PAUSED", "ERROR"],
            "EXECUTING": ["MOVING", "IDLE", "PAUSED", "ERROR"],
            "PAUSED": ["MOVING", "EXECUTING", "ERROR", "IDLE"],
            "CHARGING": ["IDLE", "MOVING", "ERROR"],
            "ERROR": ["IDLE", "UNAVAILABLE"],
            "UNAVAILABLE": ["IDLE"],
        }
        return to_state in allowed.get(from_state, [])

    def extract_position(self, state: dict) -> dict:
        """Extract agvPosition from state message."""
        pos = state.get("agvPosition", state.get("position", {}))
        return {
            "x": float(pos.get("x", 0)),
            "y": float(pos.get("y", 0)),
            "theta": float(pos.get("theta", 0)),
            "lastNodeId": pos.get("lastNodeId", ""),
            "positionInitialized": bool(pos.get("positionInitialized", False)),
        }

    def extract_errors(self, state: dict) -> list[dict]:
        """Extract and normalize error list."""
        errors = state.get("errors", [])
        if not isinstance(errors, list):
            return []
        return [
            {
                "errorType": e.get("errorType", "UNKNOWN"),
                "errorLevel": e.get("errorLevel", "WARNING"),
                "errorDescription": e.get("errorDescription", ""),
            }
            for e in errors
        ]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} brand={self.brand} versions={self.supported_versions}>"


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two semantic version strings. Returns >0 if v1>v2, 0 if equal, <0 if v1<v2."""
    parts1 = [int(x) for x in v1.split(".")]
    parts2 = [int(x) for x in v2.split(".")]
    # Pad shorter list with zeros
    while len(parts1) < len(parts2):
        parts1.append(0)
    while len(parts2) < len(parts1):
        parts2.append(0)
    for a, b in zip(parts1, parts2):
        if a != b:
            return a - b
    return 0
