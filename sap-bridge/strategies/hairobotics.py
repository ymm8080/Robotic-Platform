"""
Hai Robotics (海柔创新) strategy — Dual protocol support.

Hai robots split across two protocols:
  - HaiPick ACR Series: HAIQ-ESS REST API (proprietary)
  - HaiPort / HaiFlex: Partial VDA5050 support

Key Hai-specific concepts:
  - Tote-level tracking (not mission-level)
  - 3D storage positions (aisle/column/height)
  - Callback-based completion via HAIQ-ESS

References:
  REFERENCE/05_reference/robots/hairobotics-strategy.md
"""

from typing import Optional

from .base import BaseStrategy, RobotState, BatteryInfo, BrandQuirk


# HAIQ status → normalized status mapping
HAIQ_STATUS_MAP = {
    "IDLE": "IDLE",
    "MOVING": "MOVING",
    "WORKING": "EXECUTING",
    "RETRIEVING": "EXECUTING",
    "STORING": "EXECUTING",
    "CHARGING": "CHARGING",
    "FAULT": "ERROR",
    "OFFLINE": "OFFLINE",
    "ESTOP": "ERROR",
    "PAUSED": "PAUSED",
    "WAITING_TASK": "IDLE",
    "WAITING_PICK": "EXECUTING",
    "DOCKING": "EXECUTING",
}


class HaiRoboticsStrategy(BaseStrategy):
    """Hai Robotics — dual protocol: HAIQ-ESS REST (ACR) + VDA5050 (HaiPort/Flex)."""

    @property
    def brand(self) -> str:
        return "HaiRobotics"

    @property
    def supported_versions(self) -> list[str]:
        return ["2.0.0"]

    # ── Protocol routing ────────────────────────────────

    @staticmethod
    def get_adapter(robot_type: str = "") -> str:
        """Determine protocol adapter based on robot type.

        Returns 'haiq' for ACR series, 'vda5050' for HaiPort/HaiFlex.
        Defaults to 'haiq' (safe fallback — most Hai robots are ACR).
        """
        rt = robot_type.strip()
        if rt.upper() in ("HAIPORT", "HAIFLEX"):
            return "vda5050"
        return "haiq"

    @staticmethod
    def supports_vda5050(robot_type: str = "") -> bool:
        return HaiRoboticsStrategy.get_adapter(robot_type) == "vda5050"

    # ── Main state handler ──────────────────────────────

    def handle_state(self, state: dict) -> RobotState:
        """Route to correct handler based on robot type."""
        robot_type = state.get("robotType", state.get("type", ""))
        if self.supports_vda5050(robot_type):
            return self._map_vda5050_state(state)
        return self._map_haiq_state(state)

    # ── HAIQ-ESS handler ────────────────────────────────

    def _map_haiq_state(self, state: dict) -> RobotState:
        """Map Hai Robotics HAIQ-ESS status to normalized RobotState."""
        raw_status = state.get("taskStatus", state.get("status", "IDLE"))
        normalized = HAIQ_STATUS_MAP.get(raw_status.upper(), "UNKNOWN")

        position = self._extract_haiq_position(state)
        errors = self._extract_haiq_errors(state)
        battery_raw = state.get("batteryLevel", state.get("battery", 0))

        return RobotState(
            status=normalized,
            battery=self.normalize_battery(battery_raw),
            position=position,
            errors=errors,
            order_id=state.get("requestId", state.get("taskId")),
            operating_mode="AUTOMATIC",
            driving=(normalized == "MOVING"),
            load={
                "toteId": state.get("toteId"),
                "loadStatus": state.get("loadStatus", "unknown"),
                "weight": state.get("loadWeight", 0),
            },
            raw=state,
        )

    def _extract_haiq_position(self, state: dict) -> dict:
        """Extract position from HAIQ format — may include 3D storage coordinates."""
        loc = state.get("currentLocation", state.get("position", {}))
        if isinstance(loc, str):
            return {"locationCode": loc, "x": 0, "y": 0, "z": 0}
        return {
            "x": float(loc.get("x", loc.get("coordinateX", 0))),
            "y": float(loc.get("y", loc.get("coordinateY", 0))),
            "z": float(loc.get("z", loc.get("height", loc.get("level", 0)))),
            "aisle": loc.get("aisle", ""),
            "column": loc.get("column", ""),
            "locationCode": loc.get("station", loc.get("locationCode", "")),
        }

    def _extract_haiq_errors(self, state: dict) -> list[dict]:
        """Extract errors from HAIQ format."""
        faults = state.get("faults", state.get("errors", []))
        if not isinstance(faults, list):
            return []
        return [
            {
                "errorType": f.get("faultCode", f.get("code", "HAI-ERR")),
                "errorLevel": self._map_haiq_error_level(f.get("severity", "WARNING")),
                "errorDescription": f.get("message", f.get("description", "")),
            }
            for f in faults
        ]

    @staticmethod
    def _map_haiq_error_level(severity: str) -> str:
        mapping = {
            "INFO": "WARNING",
            "WARNING": "WARNING",
            "ERROR": "FATAL",
            "CRITICAL": "FATAL",
            "FATAL": "FATAL",
        }
        return mapping.get(severity.upper(), "WARNING")

    # ── VDA5050 handler ─────────────────────────────────

    def _map_vda5050_state(self, state: dict) -> RobotState:
        """Map HaiPort/HaiFlex VDA5050 state to normalized RobotState."""
        driving = bool(state.get("driving", False))
        paused = bool(state.get("paused", False))
        errors = self.extract_errors(state)
        error_levels = {e["errorLevel"] for e in errors}

        if "FATAL" in error_levels:
            status = "ERROR"
        elif state.get("operatingMode", "AUTOMATIC") not in ("AUTOMATIC", "SEMIAUTOMATIC"):
            status = "UNAVAILABLE"
        elif paused:
            status = "PAUSED"
        elif driving:
            status = "MOVING"
        elif state.get("actionStates"):
            running = [
                a for a in state["actionStates"]
                if a.get("actionStatus") in ("RUNNING", "INITIALIZING")
            ]
            status = "EXECUTING" if running else "IDLE"
        else:
            status = "IDLE"

        battery_raw = state.get("batteryState", {})
        return RobotState(
            status=status,
            battery=self.normalize_battery(battery_raw.get("batteryCharge", battery_raw)),
            position=self.extract_position(state),
            errors=errors,
            order_id=state.get("orderId"),
            operating_mode=self.map_operating_mode(state.get("operatingMode", "AUTOMATIC")),
            driving=driving,
            paused=paused,
            raw=state,
        )

    # ── Battery ─────────────────────────────────────────

    def normalize_battery(self, raw) -> BatteryInfo:
        """Hai Robotics reports battery as percentage (0-100)."""
        if isinstance(raw, dict):
            percent = float(raw.get("batteryCharge", raw.get("percentage", 0)))
        else:
            percent = float(raw or 0)
        return BatteryInfo(
            percent=min(100.0, max(0.0, percent)),
            charging=False,
        )

    # ── Quirks ──────────────────────────────────────────

    def get_quirks(self) -> list[BrandQuirk]:
        return [
            BrandQuirk(
                name="tote-level-tracking",
                description=(
                    "Tasks tracked at tote level, not robot mission level. "
                    "Tote ID must be mapped to SAP warehouse task."
                ),
                severity="WARN",
            ),
            BrandQuirk(
                name="haiq-callback-completion",
                description=(
                    "HAIQ-ESS pushes task completion via callback URL. "
                    "Platform must expose a callback endpoint for async notification."
                ),
                severity="WARN",
            ),
            BrandQuirk(
                name="dense-3d-storage",
                description=(
                    "Storage positions are 3D (aisle/column/height). "
                    "Standard 2D bin model needs z-axis extension."
                ),
                severity="INFO",
            ),
            BrandQuirk(
                name="acr-no-vda5050",
                description=(
                    "HaiPick ACR series does NOT support VDA5050. "
                    "Uses HAIQ-ESS REST API exclusively."
                ),
                severity="WARN",
            ),
            BrandQuirk(
                name="high-frequency-batching",
                description=(
                    "Designed for high-frequency small-tote handling. "
                    "Batch requests for efficient throughput."
                ),
                severity="INFO",
            ),
        ]
