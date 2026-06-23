"""
OTTO 1500 strategy.
VDA5050 v2.0.0 — battery in millivolts, custom charging state.
Reference: REFERENCE/05_reference/protocols/vda5050/vda5050-state-machine.md
"""
import math
from .base import BaseStrategy, RobotState, BatteryInfo, BrandQuirk

# OTTO 1500 battery curve: millivolts → approximate percentage (LiFePO4)
# Typical ranges: 48.0V (empty) → 54.6V (full) for a 48V nominal pack
_OTTO_BATTERY_MV_MIN = 48000  # 48.0V — near empty
_OTTO_BATTERY_MV_MAX = 54600  # 54.6V — fully charged
_OTTO_BATTERY_MV_RANGE = _OTTO_BATTERY_MV_MAX - _OTTO_BATTERY_MV_MIN


class OttoStrategy(BaseStrategy):
    """OTTO 1500 — VDA5050 v2.0.0 with millivolt battery."""

    @property
    def brand(self) -> str:
        return "OTTO"

    @property
    def supported_versions(self) -> list[str]:
        return ["2.0.0"]

    def handle_state(self, state: dict) -> RobotState:
        """Map OTTO 1500 state (handles mV battery + custom CHARGING).

        Known quirks:
        - Battery reported in millivolts, not percentage
        - CHARGING state reported differently than VDA5050 spec
        """
        driving = bool(state.get("driving", False))
        paused = bool(state.get("paused", False))
        errors = self.extract_errors(state)
        error_levels = {e["errorLevel"] for e in errors}
        battery_raw = state.get("batteryState", {})
        battery = self.normalize_battery(battery_raw)

        if "FATAL" in error_levels:
            status = "ERROR"
        elif state.get("operatingMode", "AUTOMATIC") not in ("AUTOMATIC", "SEMIAUTOMATIC"):
            status = "UNAVAILABLE"
        elif battery.charging:
            # OTTO reports CHARGING via batteryState.charging flag
            status = "CHARGING"
        elif paused:
            status = "PAUSED"
        elif driving:
            status = "MOVING"
        elif state.get("actionStates"):
            running = [a for a in state["actionStates"] if a.get("actionStatus") in ("RUNNING", "INITIALIZING")]
            if running:
                status = "EXECUTING"
            else:
                status = "IDLE"
        else:
            status = "IDLE"

        return RobotState(
            status=status,
            battery=battery,
            position=self.extract_position(state),
            errors=errors,
            order_id=state.get("orderId"),
            operating_mode=self.map_operating_mode(state.get("operatingMode", "AUTOMATIC")),
            driving=driving,
            paused=paused,
            raw=state,
        )

    def normalize_battery(self, raw: dict) -> BatteryInfo:
        """Convert OTTO millivolt battery reading to percentage.

        OTTO reports batteryVoltage in millivolts (e.g. 52000 = 52.0V).
        Uses LiFePO4 discharge curve approximation.
        """
        mv = raw.get("batteryVoltage")
        charge = raw.get("batteryCharge")

        if charge is not None and charge > 0:
            # Sometimes OTTO reports both — prefer batteryCharge
            percent = float(charge)
        elif mv is not None and mv > 0:
            # Convert millivolts to percentage using linear approximation
            mv_float = float(mv)
            # Clamp to valid range
            clamped = max(_OTTO_BATTERY_MV_MIN, min(_OTTO_BATTERY_MV_MAX, mv_float))
            percent = ((clamped - _OTTO_BATTERY_MV_MIN) / _OTTO_BATTERY_MV_RANGE) * 100.0
            # Round to 1 decimal
            percent = math.floor(percent * 10) / 10
        else:
            percent = 0.0

        # Detect charging: OTTO sets charging=true in batteryState or batteryVoltage near max
        charging = bool(raw.get("charging", False))
        if not charging and mv is not None:
            # If voltage is above 53.5V (near full), likely charging
            charging = float(mv) > 53500

        return BatteryInfo(
            percent=min(100.0, max(0.0, percent)),
            voltage=float(mv) / 1000 if mv else None,  # Convert mV → V for our records
            charging=charging,
        )

    def get_quirks(self) -> list[BrandQuirk]:
        return [
            BrandQuirk(
                name="battery-millivolt",
                description="OTTO reports battery in millivolts (mV), not percentage — converted via LiFePO4 curve",
                severity="WARN",
            ),
            BrandQuirk(
                name="charging-state-format",
                description="OTTO reports CHARGING via batteryState.charging flag, not as a drivingState",
                severity="INFO",
            ),
        ]
