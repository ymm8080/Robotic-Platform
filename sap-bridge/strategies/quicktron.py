"""
Quicktron (快仓) strategy — VDA5050-based with proprietary fallback.

[GUESS] VDA5050 support is unconfirmed for Quicktron newer models.
Older models use proprietary dispatch API. This strategy provides:
  - Primary: VDA5050 v2.0 / v1.1 handler
  - Fallback: generic proprietary protocol handler

References:
  REFERENCE/05_reference/robots/quicktron-strategy.md
"""


from .base import BaseStrategy, BatteryInfo, BrandQuirk, DispatchResult, RobotState


class QuicktronStrategy(BaseStrategy):
    """Quicktron (快仓) — VDA5050-based with proprietary fallback.

    [GUESS] VDA5050 support level unconfirmed — requires testing on actual robot.
    """

    @property
    def brand(self) -> str:
        return "Quicktron"

    @property
    def supported_versions(self) -> list[str]:
        # [GUESS] v1.1 and v2.0 — unconfirmed
        return ["1.1.0", "2.0.0"]

    # ── Protocol routing ────────────────────────────────

    @staticmethod
    def get_adapter(protocol_hint: str = "") -> str:
        """Determine protocol based on hint or config.

        Returns 'vda5050' by default. Switch to 'proprietary' for older robots.
        """
        hint = protocol_hint.strip().upper()
        if hint == "PROPRIETARY":
            return "proprietary"
        return "vda5050"

    # ── Main state handler ──────────────────────────────

    def handle_state(self, state: dict) -> RobotState:
        """Route based on protocol field in state."""
        protocol = state.get("protocol", state.get("_protocol", "vda5050"))
        if protocol == "proprietary":
            return self._map_proprietary_state(state)
        return self._map_vda5050_state(state)

    # ── VDA5050 handler ─────────────────────────────────

    def _map_vda5050_state(self, state: dict) -> RobotState:
        """Map Quicktron VDA5050 state to normalized RobotState.

        [GUESS] Expected to follow standard VDA5050 v2.0 with potential
        deviations in action type naming and battery format.
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
            battery=self.normalize_battery(battery_raw),
            position=self.extract_position(state),
            errors=errors,
            order_id=state.get("orderId"),
            operating_mode=self.map_operating_mode(state.get("operatingMode", "AUTOMATIC")),
            driving=driving,
            paused=paused,
            raw=state,
        )

    # ── Proprietary handler (fallback) ──────────────────

    def _map_proprietary_state(self, state: dict) -> RobotState:
        """Map Quicktron proprietary status to normalized RobotState.

        [GUESS] Structure based on typical Chinese AMR vendor APIs.
        Will need adjustment after testing on real hardware.
        """
        raw_status = state.get("taskStatus", state.get("status", "IDLE"))
        normalized = self._map_proprietary_status(raw_status)

        position = {
            "x": float(state.get("x", state.get("coordinateX", 0))),
            "y": float(state.get("y", state.get("coordinateY", 0))),
            "theta": float(state.get("theta", state.get("angle", 0))),
            "locationCode": state.get("station", state.get("locationCode", "")),
        }

        errors = self._extract_proprietary_errors(state)

        return RobotState(
            status=normalized,
            battery=self.normalize_battery(state.get("batteryLevel", state.get("battery", 0))),
            position=position,
            errors=errors,
            order_id=state.get("orderId", state.get("missionId")),
            operating_mode="AUTOMATIC",
            driving=(normalized == "MOVING"),
            raw=state,
        )

    @staticmethod
    def _map_proprietary_status(status: str) -> str:
        """Map Quicktron proprietary statuses."""
        mapping = {
            "IDLE": "IDLE",
            "RUNNING": "MOVING",
            "WORKING": "EXECUTING",
            "CHARGING": "CHARGING",
            "FAULT": "ERROR",
            "OFFLINE": "OFFLINE",
            "ESTOP": "ERROR",
            "PAUSE": "PAUSED",
            "DOCKING": "EXECUTING",
        }
        return mapping.get(status.upper(), "UNKNOWN")

    def _extract_proprietary_errors(self, state: dict) -> list[dict]:
        """Extract errors from proprietary format."""
        faults = state.get("faults", state.get("errors", []))
        if not isinstance(faults, list):
            return []
        return [
            {
                "errorType": f.get("code", f.get("faultCode", "QT-ERR")),
                "errorLevel": self._map_proprietary_error_level(f.get("level", "WARNING")),
                "errorDescription": f.get("message", f.get("description", "")),
            }
            for f in faults
        ]

    @staticmethod
    def _map_proprietary_error_level(level: str) -> str:
        mapping = {
            "INFO": "WARNING",
            "WARN": "WARNING",
            "WARNING": "WARNING",
            "ERROR": "FATAL",
            "FATAL": "FATAL",
        }
        return mapping.get(level.upper(), "WARNING")

    # ── Battery ─────────────────────────────────────────

    def normalize_battery(self, raw) -> BatteryInfo:
        """Quicktron battery — [GUESS] format may vary (mV vs %)."""
        if isinstance(raw, dict):
            # Try VDA5050 standard first, then check for mV
            charge = raw.get("batteryCharge")
            if charge is not None:
                percent = float(charge)
            else:
                # [GUESS] Might report in mV — convert if > 100
                mv = float(raw.get("batteryVoltage", raw.get("voltage", 0)))
                percent = self._millivolts_to_percent(mv) if mv > 100 else float(raw.get("percentage", 0))
        else:
            val = float(raw or 0)
            # [GUESS] If value > 100, assume millivolts
            percent = self._millivolts_to_percent(val) if val > 100 else val

        return BatteryInfo(
            percent=min(100.0, max(0.0, percent)),
            charging=False,
        )

    def dispatch(self, order: dict) -> DispatchResult:
        """Build dispatch payload for Quicktron — routes to VDA5050 or proprietary."""
        order_id = order.get("orderId", "")
        protocol_hint = order.get("protocol", order.get("_protocol", "vda5050"))
        adapter = self.get_adapter(protocol_hint)

        if adapter == "vda5050":
            return DispatchResult(
                success=True,
                order_id=order_id,
                protocol="vda5050",
                payload={
                    "orderId": order_id,
                    "orderUpdateId": order.get("orderUpdateId", 0),
                    "nodes": order.get("nodes", []),
                    "edges": order.get("edges", []),
                },
            )
        # Proprietary format
        return DispatchResult(
            success=True,
            order_id=order_id,
            protocol="rest",
            payload={
                "missionId": order_id,
                "robotId": order.get("robotId", order.get("serialNumber", "")),
                "taskType": order.get("taskType", "MOVE"),
                "station": order.get("target", ""),
                "priority": order.get("priority", 3),
            },
        )

    @staticmethod
    def _millivolts_to_percent(mv: float) -> float:
        """Convert millivolts to percentage.

        [GUESS] Using typical 24V LiFePO4 curve:
          - 29.2V (29200 mV) = 100%
          - 21.0V (21000 mV) = 0%
        """
        if mv >= 29200:
            return 100.0
        if mv <= 21000:
            return 0.0
        return ((mv - 21000) / (29200 - 21000)) * 100.0

    # ── Quirks ──────────────────────────────────────────

    def get_quirks(self) -> list[BrandQuirk]:
        return [
            BrandQuirk(
                name="vda5050-unconfirmed",
                description=(
                    "[GUESS] VDA5050 support level unconfirmed. "
                    "Requires testing on actual robot. Falls back to proprietary protocol."
                ),
                severity="WARN",
            ),
            BrandQuirk(
                name="battery-format-unknown",
                description=(
                    "[GUESS] Battery reporting format may be mV or %. "
                    "Adaptive conversion applied — verify on real hardware."
                ),
                severity="WARN",
            ),
            BrandQuirk(
                name="chinese-topic-prefix",
                description=(
                    "[GUESS] May use 'uagv/v2/' MQTT topic prefix. "
                    "Verify topic structure during integration testing."
                ),
                severity="INFO",
            ),
        ]
