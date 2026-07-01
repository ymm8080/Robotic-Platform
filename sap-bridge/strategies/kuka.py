"""
KUKA KMR iiwa strategy.
VDA5050 v2.0.0 — standard behavior with custom lift action.
"""
from .base import BaseStrategy, BatteryInfo, BrandQuirk, RobotState


class KukaStrategy(BaseStrategy):
    """KUKA KMR iiwa — VDA5050 v2.0.0 compliant."""

    @property
    def brand(self) -> str:
        return "KUKA"

    @property
    def supported_versions(self) -> list[str]:
        return ["2.0.0"]

    def handle_state(self, state: dict) -> RobotState:
        """Map KUKA VDA5050 state to normalized RobotState."""
        # Determine status from driving + action states
        driving = bool(state.get("driving", False))
        paused = bool(state.get("paused", False))
        errors = self.extract_errors(state)
        error_levels = {e["errorLevel"] for e in errors}

        if "FATAL" in error_levels:
            status = "ERROR"
        elif state.get("operatingMode", "AUTOMATIC") not in ("AUTOMATIC", "SEMIAUTOMATIC"):
            status = "UNAVAILABLE"
        elif state.get("batteryState", {}).get("batteryCharge", 0) <= 5:
            # KUKA specific: battery at or below 5% triggers CHARGING
            status = "CHARGING"
        elif paused:
            status = "PAUSED"
        elif driving:
            status = "MOVING"
        elif state.get("actionStates"):
            # Has active actions → EXECUTING
            running = [a for a in state["actionStates"] if a.get("actionStatus") in ("RUNNING", "INITIALIZING")]
            status = "EXECUTING" if running else "IDLE"
        else:
            status = "IDLE"

        battery_raw = state.get("batteryState", {})
        return RobotState(
            status=status,
            battery=self.normalize_battery(battery_raw),
            position=self.extract_position(state),
            errors=errors,
            order_id=state.get("orderId"),
            operating_mode=self.map_operating_mode(state.get("operatingMode", "AUTOMATIC")),
            driving=driving,
            paused=paused,
            raw=state,
        )

    def normalize_battery(self, raw: dict) -> BatteryInfo:
        """KUKA reports standard percentage + voltage."""
        return BatteryInfo(
            percent=float(raw.get("batteryCharge", 0)),
            voltage=float(raw.get("batteryVoltage", 0)) if raw.get("batteryVoltage") else None,
            health=float(raw.get("batteryHealth", 0)) if raw.get("batteryHealth") else None,
            charging=False,  # KUKA reports charging via driving=false + batteryState
        )

    def get_quirks(self) -> list[BrandQuirk]:
        return [
            BrandQuirk(
                name="lift-action-requires-pre-navigate",
                description="Lift action requires a preceding navigate action; lift height in mm",
                severity="WARN",
            ),
            BrandQuirk(
                name="standard-vda5050-v2",
                description="KUKA follows VDA5050 v2.0.0 closely — minimal deviations expected",
                severity="INFO",
            ),
        ]
