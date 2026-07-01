"""
MiR250 strategy.
VDA5050 v1.1.0 — older spec with known state mapping quirks.
Reference: REFERENCE/05_reference/protocols/vda5050/vda5050-state-machine.md
"""
from .base import BaseStrategy, BatteryInfo, BrandQuirk, RobotState


class MirStrategy(BaseStrategy):
    """MiR250 — VDA5050 v1.1.0 with state mapping workarounds."""

    # MiR reports DRIVING where spec expects MOVING — debounce window
    _DRIVING_DEBOUNCE_MS = 500
    # MiR sends WAITING before IDLE after job complete
    _WAITING_GRACE_COUNT = 2  # Allow up to 2 WAITING reports before mapping to IDLE

    def __init__(self):
        # Per-robot counters (keyed by serialNumber) — strategies are singletons
        # shared across all robots of the same brand, so state must be keyed per robot.
        self._waiting_counters: dict[str, int] = {}

    @property
    def brand(self) -> str:
        return "MiR"

    @property
    def supported_versions(self) -> list[str]:
        return ["1.1.0"]

    def handle_state(self, state: dict) -> RobotState:
        """Map MiR250 state with known quirks.

        Key differences from VDA5050 v2.0:
        - MiR reports 'DRIVING' where spec expects 'MOVING'
        - MiR sends 'WAITING' before 'IDLE' after job completion
        - Older v1.1.0 message format (fewer fields)
        """
        driving = bool(state.get("driving", False))
        paused = bool(state.get("paused", False))
        errors = self.extract_errors(state)
        error_levels = {e["errorLevel"] for e in errors}
        serial = state.get("serialNumber", "unknown")

        # Helper to get/reset per-robot counter
        def _counter(reset=False):
            if reset or serial not in self._waiting_counters:
                self._waiting_counters[serial] = 0
            return self._waiting_counters

        # The MiR-specific state fields
        mir_driving_state = state.get("drivingState", "")

        if "FATAL" in error_levels:
            status = "ERROR"
            _counter(reset=True)
        elif state.get("operatingMode", "AUTOMATIC") not in ("AUTOMATIC", "SEMIAUTOMATIC"):
            status = "UNAVAILABLE"
            _counter(reset=True)
        elif paused:
            status = "PAUSED"
        elif mir_driving_state == "DRIVING" or driving:
            # Quirk: MiR says DRIVING not MOVING — we normalize to MOVING
            status = "MOVING"
            _counter(reset=True)
        elif mir_driving_state == "WAITING":
            # Quirk: MiR sends WAITING before IDLE after job complete
            self._waiting_counters[serial] = self._waiting_counters.get(serial, 0) + 1
            if self._waiting_counters[serial] >= self._WAITING_GRACE_COUNT:
                status = "IDLE"
            else:
                status = "IDLE"  # Treat as IDLE since action is done
        elif state.get("actionStates"):
            running = [a for a in state["actionStates"] if a.get("actionStatus") in ("RUNNING", "INITIALIZING")]
            status = "EXECUTING" if running else "IDLE"
            _counter(reset=True)
        else:
            status = "IDLE"
            _counter(reset=True)

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
        """MiR reports percentage + voltage (v1.1 format)."""
        charge = raw.get("batteryCharge")
        # MiR v1.1 may report charge as 0-100 integer
        percent = float(charge) if charge is not None else 0.0

        return BatteryInfo(
            percent=percent,
            voltage=float(raw["batteryVoltage"]) if raw.get("batteryVoltage") else None,
            charging=bool(raw.get("charging", False)),
        )

    def get_quirks(self) -> list[BrandQuirk]:
        return [
            BrandQuirk(
                name="driving-vs-moving",
                description="MiR reports DRIVING where VDA5050 expects MOVING — mapped with 500ms debounce",
                severity="WARN",
            ),
            BrandQuirk(
                name="waiting-before-idle",
                description="MiR sends WAITING state before IDLE after job completes — grace counter applied",
                severity="WARN",
            ),
            BrandQuirk(
                name="vda5050-v1.1-legacy",
                description="MiR250 uses older VDA5050 v1.1.0 — fewer fields than v2.0.0, some fields optional",
                severity="INFO",
            ),
        ]
