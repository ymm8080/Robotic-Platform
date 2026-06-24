"""
Geek+ (极智嘉) strategy — Dual protocol support.

Geek+ robot lines split across two protocols:
  - P-Series (Picking), S-Series (Sorting): IOP REST API (no VDA5050)
  - M-Series (Moving), R-Series (Roller): VDA5050 v2.0.0

The strategy detects the robot model and routes to the correct handler.

References:
  REFERENCE/05_reference/robots/geekplus-strategy.md
"""


from .base import BaseStrategy, BatteryInfo, BrandQuirk, RobotState

# IOP status → normalized status mapping
IOP_STATUS_MAP = {
    "IDLE": "IDLE",
    "MOVING": "MOVING",
    "WORKING": "EXECUTING",
    "CHARGING": "CHARGING",
    "FAULT": "ERROR",
    "OFFLINE": "OFFLINE",
    "EMERGENCY_STOP": "ERROR",
    "PAUSED": "PAUSED",
    "WAITING": "IDLE",
    "DOCKING": "EXECUTING",
    "LIFTING": "EXECUTING",
}


class GeekPlusStrategy(BaseStrategy):
    """Geek+ — dual protocol: IOP REST (P/S series) + VDA5050 (M/R series)."""

    @property
    def brand(self) -> str:
        return "GeekPlus"

    @property
    def supported_versions(self) -> list[str]:
        return ["1.1.0", "2.0.0"]

    # ── Protocol routing ────────────────────────────────

    @staticmethod
    def get_adapter(robot_model: str = "") -> str:
        """Determine which protocol adapter to use based on robot model.

        Returns 'iop' for P/S series, 'vda5050' for M/R series.
        Defaults to 'iop' for unknown models (safe fallback).
        """
        prefix = robot_model.strip().upper()[:1] if robot_model else ""
        if prefix in ("M", "R"):
            return "vda5050"
        return "iop"

    @staticmethod
    def supports_vda5050(robot_model: str = "") -> bool:
        """Check if this robot model supports VDA5050."""
        return GeekPlusStrategy.get_adapter(robot_model) == "vda5050"

    # ── Main state handler ──────────────────────────────

    def handle_state(self, state: dict) -> RobotState:
        """Route to correct handler based on robot model."""
        robot_model = state.get("robotModel", state.get("model", ""))
        if self.supports_vda5050(robot_model):
            return self._map_vda5050_state(state)
        return self._map_iop_state(state)

    # ── IOP REST handler ────────────────────────────────

    def _map_iop_state(self, state: dict) -> RobotState:
        """Map Geek+ IOP REST API response to normalized RobotState."""
        raw_status = state.get("taskStatus", state.get("status", "IDLE"))
        normalized = IOP_STATUS_MAP.get(raw_status.upper(), "UNKNOWN")

        # Extract position from IOP format (may be "location" or "position")
        position = self._extract_iop_position(state)

        # IOP reports faults as array or nested
        errors = self._extract_iop_errors(state)

        # Battery: percentage only
        battery_raw = state.get("batteryLevel", state.get("battery", 0))

        return RobotState(
            status=normalized,
            battery=self.normalize_battery(battery_raw),
            position=position,
            errors=errors,
            order_id=state.get("missionId", state.get("orderId")),
            operating_mode="AUTOMATIC",
            driving=(normalized == "MOVING"),
            load={"weight": state.get("loadWeight", state.get("load", 0))},
            raw=state,
        )

    def _extract_iop_position(self, state: dict) -> dict:
        """Extract position from IOP format."""
        loc = state.get("location", state.get("position", {}))
        if isinstance(loc, str):
            return {"locationCode": loc, "x": 0, "y": 0, "theta": 0}
        return {
            "x": float(loc.get("x", loc.get("coordinateX", 0))),
            "y": float(loc.get("y", loc.get("coordinateY", 0))),
            "theta": float(loc.get("theta", loc.get("angle", 0))),
            "locationCode": loc.get("locationCode", loc.get("station", "")),
        }

    def _extract_iop_errors(self, state: dict) -> list[dict]:
        """Extract errors from IOP format."""
        faults = state.get("faults", state.get("errors", []))
        if not isinstance(faults, list):
            return []
        return [
            {
                "errorType": f.get("faultCode", f.get("code", "UNKNOWN")),
                "errorLevel": self._map_iop_error_level(f.get("level", f.get("severity", "WARNING"))),
                "errorDescription": f.get("message", f.get("description", "")),
            }
            for f in faults
        ]

    @staticmethod
    def _map_iop_error_level(level: str) -> str:
        mapping = {
            "INFO": "WARNING",
            "WARNING": "WARNING",
            "ERROR": "FATAL",
            "FATAL": "FATAL",
            "CRITICAL": "FATAL",
        }
        return mapping.get(level.upper(), "WARNING")

    # ── VDA5050 handler ─────────────────────────────────

    def _map_vda5050_state(self, state: dict) -> RobotState:
        """Map Geek+ VDA5050 state to normalized RobotState.

        Geek+ M/R series follow standard VDA5050 v2.0.0 with minimal quirks.
        """
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
        """Geek+ reports percentage only — no voltage."""
        if isinstance(raw, dict):
            percent = float(raw.get("batteryCharge", raw.get("percentage", 0)))
        else:
            percent = float(raw or 0)
        return BatteryInfo(
            percent=min(100.0, max(0.0, percent)),
            charging=False,  # Determined from state, not battery reading
        )

    # ── Quirks ──────────────────────────────────────────

    def get_quirks(self) -> list[BrandQuirk]:
        return [
            BrandQuirk(
                name="iop-mission-polling",
                description=(
                    "IOP missions require polling GET /mission/{id}/status for completion. "
                    "No push notification available."
                ),
                severity="WARN",
            ),
            BrandQuirk(
                name="series-split",
                description=(
                    "P/S series use proprietary IOP REST API. "
                    "M/R series support VDA5050 v2.0.0."
                ),
                severity="WARN",
            ),
            BrandQuirk(
                name="battery-percentage-only",
                description="Geek+ reports battery as percentage only. No voltage data available.",
                severity="INFO",
            ),
            BrandQuirk(
                name="manufacturer-field-case",
                description="VDA5050 manufacturer field uses 'GeekPlus' (camelCase). Not 'GEEK+' or 'GEEKPLUS'.",
                severity="INFO",
            ),
            BrandQuirk(
                name="iop-chinese-cloud-latency",
                description="IOP may be hosted in Alibaba Cloud China. Expect higher latency for non-Asia deployments.",
                severity="INFO",
            ),
        ]
