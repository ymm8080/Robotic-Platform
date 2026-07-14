"""Brand strategy classes — vendor-specific VDA5050 → FleetState translation.

Each strategy implements the ``_StrategyLike`` protocol expected by
``VDA5050FleetAdapter`` and lives entirely in the core so there is zero
dependency on ``sap-bridge/strategies/``.

Relationship to ``sap-bridge/strategies/``:
  - This module (core): canonical strategy layer for the v5.0 traffic
    coordinator.  Lightweight, standalone classes, uses core Pose /
    FleetState / SensorHealth, accepts MapTransformer.
  - sap-bridge/strategies/: SAP integration layer with richer features
    (ABC base, version checking, BrandQuirk, DispatchResult).  Used
    by the SAP bridge service for OData/RFC/IDoc integration.
  - The two layers are intentionally separate: core has zero dependency on
    sap-bridge.  If a future phase merges them, sap-bridge/strategies/
    should delegate to these core classes, not the reverse.

Brand quirks handled:
  - MiR:  reports driving state as VDA5050 operatingMode string, no robotId
          in state payload (derived from MQTT topic).
  - OTTO: battery reported in millivolts; operatingMode key is ``mode`` not
          ``operatingMode``.
  - KUKA: KMP series uses ``agvMode`` and ``batteryState.charge`` fields.
  - Geek+:  proprietary P_VDA5050 envelope wrapping standard state.
  - HaiRobotics: HaiPick ACR (shelf-to-person) — reports ``robotMode`` +
                 ``taskStatusCode``.
  - Quicktron: QuickBin VDA5050-compatible with Chinese error codes.

All strategies accept an optional ``MapTransformer``; if omitted, the
identity transformer is used (robot coordinates are already in the unified
frame).
"""

from __future__ import annotations

from core.adapter.brands.brand_knowledge import get_brand_knowledge
from core.adapter.map_transformer import MapTransformer
from core.messages import (
    ActionPrimitive,
    CapabilityVector,
    EnvConstraints,
    FleetState,
    HealthStatus,
    Pose,
    RobotMode,
    SensorHealth,
)

# ── VDA5050 operatingMode → RobotMode mapping (shared across brands) ──

_VDA5050_MODE_MAP: dict[str, RobotMode] = {
    "IDLE": RobotMode.IDLE,
    "AUTOMATIC": RobotMode.IDLE,  # ready for task, not currently executing
    "MANUAL": RobotMode.IDLE,
    "SEMIAUTOMATIC": RobotMode.IDLE,
    "TEACHIN": RobotMode.IDLE,
    "SERVICE": RobotMode.IDLE,
    "TASKING": RobotMode.TASKING,
    "DRIVING": RobotMode.TASKING,
    "MOVING": RobotMode.TASKING,
    "CHARGING": RobotMode.CHARGING,
    "ERROR": RobotMode.ERROR,
    "PAUSED": RobotMode.IDLE,
    "SUSPENDED": RobotMode.IDLE,
}

_MILLIVOLT_TO_PERCENT = 0.004  # OTTO: 25000 mV ≈ 100 %


def _normalise_battery(raw_val: float, raw_unit: str = "percent") -> float:
    """Return 0–100 battery percentage regardless of vendor format."""
    unit = raw_unit.strip().lower()
    if unit in ("mv", "millivolt", "millivolts"):
        return max(0.0, min(100.0, raw_val * _MILLIVOLT_TO_PERCENT))
    if unit in ("v", "volt", "volts"):
        return max(0.0, min(100.0, raw_val * 2.083))  # 48 V → 100 %
    # assume percent already
    return max(0.0, min(100.0, float(raw_val)))


def _parse_pose(payload: dict) -> Pose:
    """Extract Pose from a VDA5050 ``agvPosition`` block or equivalent."""
    pos = payload.get("agvPosition", payload)
    x = float(pos.get("x", 0.0))
    y = float(pos.get("y", 0.0))
    theta = float(pos.get("theta", 0.0))
    position_initialized = bool(pos.get("positionInitialized", True))
    last_node = pos.get("nodeId", pos.get("lastNodeId", ""))
    return Pose(
        x=x,
        y=y,
        theta=theta,
        position_initialized=position_initialized,
        last_node_id=str(last_node),
    )


def _apply_transform(transformer: MapTransformer | None, pose: Pose) -> Pose:
    """Apply ``MapTransformer.transform_pose`` to a Pose.

    Preserves ``position_initialized`` and ``last_node_id`` -- only the
    spatial components (x, y, theta) are transformed.

    If ``transformer`` is ``None``, the pose is returned unchanged.
    """
    if transformer is None:
        return pose
    t = transformer.transform_pose(pose.x, pose.y, pose.theta)
    return Pose(
        x=t.x,
        y=t.y,
        theta=t.theta,
        position_initialized=pose.position_initialized,
        last_node_id=pose.last_node_id,
    )


def _parse_vda5050_mode(payload: dict) -> RobotMode:
    """Extract RobotMode from standard VDA5050 operatingMode."""
    mode_str = payload.get("operatingMode", payload.get("mode", "IDLE")).strip().upper()
    return _VDA5050_MODE_MAP.get(mode_str, RobotMode.IDLE)


def _parse_vda5050_errors(payload: dict) -> list[str]:
    """Extract normalized error strings from VDA5050 error list."""
    errors = payload.get("errors", []) or []
    out: list[str] = []
    for e in errors:
        if isinstance(e, str):
            out.append(e)
            continue
        typ = e.get("errorType", e.get("type", "UNKNOWN"))
        lvl = e.get("errorLevel", e.get("level", "WARN"))
        desc = e.get("errorDescription", e.get("description", ""))
        refs = e.get("errorReferences", [])
        ref_str = f" [{','.join(str(r.get('referenceKey', '')) for r in refs)}]" if refs else ""
        out.append(f"{typ}:{lvl}:{desc}{ref_str}")
    return out


def _capability_from_knowledge(brand: str) -> CapabilityVector:
    """Build a CapabilityVector from the shared brand-knowledge registry.

    Phase 0 dedup: the DISPATCH side no longer hardcodes per-brand capability
    facts — they are sourced from ``core.adapter.brands.brand_knowledge`` so the
    DISPATCH and SAP layers cannot drift apart. Values are verified identical to
    the previously-hardcoded vectors across all six brands (see
    ``01_architecture/PHASE0_DUAL_STRATEGY_FINDING.md``).
    """
    cv = get_brand_knowledge(brand).default_capability_vector
    return CapabilityVector(
        payload_kg=cv["payload_kg"],
        max_speed=cv["max_speed"],
        supported_models=list(cv["supported_models"]),
        action_primitives={ActionPrimitive[p] for p in cv["action_primitives"]},
        env=EnvConstraints(**cv["env"]),
        supports_reverse=cv["supports_reverse"],
    )


# ═══════════════════════════════════════════════════════════════════
#  MiR Strategy
# ═══════════════════════════════════════════════════════════════════


class MirStrategy:
    """MiR (Mobile Industrial Robots) VDA5050 strategy.

    Quirks:
      - May report ``robotId`` as ``MiR_<serial>``; topic-derived id is preferred.
      - Reports ``operatingMode`` as ``AUTOMATIC`` when driving.
      - MiR REST API provides additional state fields not in VDA5050 (position
        accuracy, mission queue depth). These are ingested as-is and surfaced
        in FleetState via the ``raw_state`` passthrough.
    """

    brand = "mir"

    def __init__(self, transformer: MapTransformer | None = None) -> None:
        self._transformer = transformer or MapTransformer.identity("mir")

    def handle_state(self, raw: dict) -> MirState:
        robot_id = raw.get("robotId", raw.get("robot_id", raw.get("serialNumber", "mir_unknown")))
        pose_raw = raw.get("agvPosition", {})
        x, y, theta = (
            float(pose_raw.get("x", 0)),
            float(pose_raw.get("y", 0)),
            float(pose_raw.get("theta", 0)),
        )

        battery_raw = raw.get("batteryState", raw.get("battery", {}))
        battery = _normalise_battery(
            float(battery_raw.get("batteryCharge", 100.0)),
            str(battery_raw.get("charging", "percent")),
        )

        loads = raw.get("loads", raw.get("load", [])) or []
        has_load = any(ld.get("loadPosition", ld.get("position", "")) != "" for ld in loads)

        pose = Pose(
            x=x,
            y=y,
            theta=theta,
            position_initialized=bool(pose_raw.get("positionInitialized", True)),
            last_node_id=str(pose_raw.get("nodeId", "")),
        )
        pose = _apply_transform(self._transformer, pose)

        return MirState(
            robot_id=str(robot_id),
            pose=pose,
            battery_percent=battery,
            mode=RobotMode.TASKING if has_load and bool(pose_raw) else _parse_vda5050_mode(raw),
            velocity=float(raw.get("velocity", raw.get("speed", 0.0))),
            errors=_parse_vda5050_errors(raw),
            sensor_health=_parse_mir_sensor_health(raw),
        )

    def to_fleet_state(self, robot_state: MirState) -> FleetState:
        return FleetState(
            robot_id=robot_state.robot_id,
            boot_id=robot_state.boot_id,
            pose=robot_state.pose,
            battery_percent=robot_state.battery_percent,
            mode=robot_state.mode,
            errors=robot_state.errors,
            sensor_health=robot_state.sensor_health,
            velocity=robot_state.velocity,
            capability=self.to_capability_vector(),
        )

    def to_capability_vector(self) -> CapabilityVector:
        return _capability_from_knowledge("mir")

    def extract_errors(self, state: dict) -> list[dict]:
        raw_errors = state.get("errors", []) or []
        if isinstance(raw_errors, list):
            return raw_errors
        return []

    def dispatch(self, order: dict) -> dict:
        return {
            "mission": order.get("orderId", ""),
            "parameters": [{"key": "path", "value": ",".join(order.get("path", []))}],
        }


class MirState:
    """Intermediate robot state for MiR."""

    __slots__ = (
        "robot_id",
        "boot_id",
        "pose",
        "battery_percent",
        "mode",
        "velocity",
        "errors",
        "sensor_health",
        "has_load",
    )

    def __init__(
        self,
        robot_id: str,
        pose: Pose,
        battery_percent: float,
        mode: RobotMode,
        velocity: float,
        errors: list[str],
        sensor_health: SensorHealth,
        boot_id: str = "",
        has_load: bool = False,
    ) -> None:
        self.robot_id = robot_id
        self.boot_id = boot_id
        self.pose = pose
        self.battery_percent = battery_percent
        self.mode = mode
        self.velocity = velocity
        self.errors = errors
        self.sensor_health = sensor_health
        self.has_load = has_load


def _parse_mir_sensor_health(raw: dict) -> SensorHealth:
    safety = raw.get("safetyState", raw.get("safety", {}))
    e_stop = safety.get("eStop", "none")
    field = safety.get("fieldViolation", False)
    if e_stop != "none" or field:
        return SensorHealth(
            velocity_sensor=HealthStatus.DEGRADED,
            lidar=HealthStatus.DEGRADED,
            camera=HealthStatus.HEALTHY,
            time_sync=HealthStatus.HEALTHY,
        )
    return SensorHealth()


# ═══════════════════════════════════════════════════════════════════
#  OTTO Strategy
# ═══════════════════════════════════════════════════════════════════


class OttoStrategy:
    """OTTO Motors VDA5050 strategy.

    Quirks:
      - Battery in millivolts (e.g. 25000 → 100 %).
      - ``mode`` key instead of ``operatingMode`` in some firmware versions.
      - Uses ``batteryPercentage`` and ``batteryVoltage`` parallel fields.
      - OTTO health includes ``motorTemperature`` and ``driveState``.
    """

    brand = "otto"

    def __init__(self, transformer: MapTransformer | None = None) -> None:
        self._transformer = transformer or MapTransformer.identity("otto")

    def handle_state(self, raw: dict) -> OttoState:
        robot_id = raw.get("robotId", raw.get("robot_id", raw.get("serialNumber", "otto_unknown")))
        pose = _parse_pose(raw)
        pose = _apply_transform(self._transformer, pose)

        battery_raw = raw.get("batteryState", raw.get("battery", {}))
        battery_charge = float(
            battery_raw.get("batteryCharge", battery_raw.get("batteryPercentage", 50.0))
        )
        battery_unit = str(battery_raw.get("charging", battery_raw.get("unit", "percent")))
        battery = _normalise_battery(battery_charge, battery_unit)

        health = HealthStatus.HEALTHY
        motor_temp = float(raw.get("motorTemperature", battery_raw.get("motorTemperature", 30.0)))
        if motor_temp > 75.0:
            health = SensorHealth.DEGRADED
        elif motor_temp > 90.0:
            health = SensorHealth.CRITICAL

        return OttoState(
            robot_id=str(robot_id),
            pose=pose,
            battery_percent=battery,
            mode=_parse_vda5050_mode(raw),
            velocity=float(raw.get("velocity", 0.0)),
            errors=_parse_vda5050_errors(raw),
            sensor_health=SensorHealth(
                velocity_sensor=HealthStatus(health),
                lidar=HealthStatus.HEALTHY,
                camera=HealthStatus.HEALTHY,
                time_sync=HealthStatus.HEALTHY,
            ),
            motor_temperature=motor_temp,
        )

    def to_fleet_state(self, robot_state: OttoState) -> FleetState:
        return FleetState(
            robot_id=robot_state.robot_id,
            boot_id=robot_state.boot_id,
            pose=robot_state.pose,
            battery_percent=robot_state.battery_percent,
            mode=robot_state.mode,
            errors=robot_state.errors,
            sensor_health=robot_state.sensor_health,
            velocity=robot_state.velocity,
            capability=self.to_capability_vector(),
        )

    def to_capability_vector(self) -> CapabilityVector:
        return _capability_from_knowledge("otto")

    def extract_errors(self, state: dict) -> list[dict]:
        return state.get("errors", []) or []

    def dispatch(self, order: dict) -> dict:
        return {"job": order.get("orderId", ""), "destinations": [order.get("destination", "")]}


class OttoState:
    __slots__ = (
        "robot_id",
        "boot_id",
        "pose",
        "battery_percent",
        "mode",
        "velocity",
        "errors",
        "sensor_health",
        "motor_temperature",
    )

    def __init__(
        self,
        robot_id: str,
        pose: Pose,
        battery_percent: float,
        mode: RobotMode,
        velocity: float,
        errors: list[str],
        sensor_health: SensorHealth,
        motor_temperature: float = 30.0,
        boot_id: str = "",
    ) -> None:
        self.robot_id = robot_id
        self.boot_id = boot_id
        self.pose = pose
        self.battery_percent = battery_percent
        self.mode = mode
        self.velocity = velocity
        self.errors = errors
        self.sensor_health = sensor_health
        self.motor_temperature = motor_temperature


# ═══════════════════════════════════════════════════════════════════
#  KUKA Strategy
# ═══════════════════════════════════════════════════════════════════


class KukaStrategy:
    """KUKA KMP series VDA5050 strategy.

    Quirks:
      - ``agvMode`` used instead of ``operatingMode`` in older firmware.
      - Battery reported as ``batteryState.charge`` (0–100) or ``batteryCharge``.
      - Load info under ``load`` (singular) not ``loads`` (plural) in some versions.
      - KUKA KMP 1500 has different max speed from KMP 600.
    """

    brand = "kuka"

    def __init__(self, transformer: MapTransformer | None = None) -> None:
        self._transformer = transformer or MapTransformer.identity("kuka")

    def handle_state(self, raw: dict) -> KukaState:
        robot_id = raw.get("robotId", raw.get("robot_id", raw.get("serialNumber", "kuka_unknown")))
        pose = _parse_pose(raw)
        pose = _apply_transform(self._transformer, pose)

        battery_raw = raw.get("batteryState", raw.get("battery", {}))
        battery = _normalise_battery(
            float(battery_raw.get("batteryCharge", battery_raw.get("charge", 100.0)))
        )

        # KUKA agvMode → RobotMode
        agv_mode = raw.get("agvMode", raw.get("operatingMode", "IDLE")).strip().upper()
        mode = _VDA5050_MODE_MAP.get(agv_mode, RobotMode.IDLE)

        return KukaState(
            robot_id=str(robot_id),
            pose=pose,
            battery_percent=battery,
            mode=mode,
            velocity=float(raw.get("velocity", 0.0)),
            errors=_parse_vda5050_errors(raw),
            sensor_health=SensorHealth(),
        )

    def to_fleet_state(self, robot_state: KukaState) -> FleetState:
        return FleetState(
            robot_id=robot_state.robot_id,
            boot_id=robot_state.boot_id,
            pose=robot_state.pose,
            battery_percent=robot_state.battery_percent,
            mode=robot_state.mode,
            errors=robot_state.errors,
            sensor_health=robot_state.sensor_health,
            velocity=robot_state.velocity,
            capability=self.to_capability_vector(),
        )

    def to_capability_vector(self) -> CapabilityVector:
        return _capability_from_knowledge("kuka")

    def extract_errors(self, state: dict) -> list[dict]:
        return state.get("errors", []) or []

    def dispatch(self, order: dict) -> dict:
        return {
            "orderId": order.get("orderId", ""),
            "nodes": [
                {"nodeId": n, "sequenceId": i, "released": True}
                for i, n in enumerate(order.get("path", []))
            ],
        }


class KukaState:
    __slots__ = (
        "robot_id",
        "boot_id",
        "pose",
        "battery_percent",
        "mode",
        "velocity",
        "errors",
        "sensor_health",
    )

    def __init__(
        self,
        robot_id: str,
        pose: Pose,
        battery_percent: float,
        mode: RobotMode,
        velocity: float,
        errors: list[str],
        sensor_health: SensorHealth,
        boot_id: str = "",
    ) -> None:
        self.robot_id = robot_id
        self.boot_id = boot_id
        self.pose = pose
        self.battery_percent = battery_percent
        self.mode = mode
        self.velocity = velocity
        self.errors = errors
        self.sensor_health = sensor_health


# ═══════════════════════════════════════════════════════════════════
#  Geek+ Strategy
# ═══════════════════════════════════════════════════════════════════


class GeekPlusStrategy:
    """Geek+ (极智嘉) P_VDA5050 strategy.

    Quirks:
      - Proprietary ``P_VDA5050`` envelope: the VDA5050 state is nested inside
        a ``data`` key with extra fields (``robotModel``, ``warehouseId``,
        ``zoneId``).
      - Uses ``sysStatus`` and ``taskStatus`` rather than VDA5050 ``operatingMode``.
      - Coordinate origin is warehouse-local; needs MapTransformer.
      - Action primitives include SHELF_CARRY (carrying a shelf pod).
    """

    brand = "geekplus"

    def __init__(self, transformer: MapTransformer | None = None) -> None:
        self._transformer = transformer or MapTransformer.identity("geekplus")

    def handle_state(self, raw: dict) -> GeekPlusState:
        # Unwrap P_VDA5050 envelope if present
        if "data" in raw:
            raw = raw["data"]

        robot_id = raw.get("robotId", raw.get("robot_id", raw.get("deviceId", "geek_unknown")))
        pose = _parse_pose(raw)
        pose = _apply_transform(self._transformer, pose)

        battery_raw = raw.get("batteryState", raw.get("battery", {}))
        battery = _normalise_battery(
            float(battery_raw.get("batteryCharge", battery_raw.get("percentage", 100.0)))
        )

        # Geek+ sysStatus → RobotMode
        sys_status = raw.get("sysStatus", raw.get("operatingMode", "IDLE")).strip().upper()
        mode_map = {
            "IDLE": RobotMode.IDLE,
            "STANDBY": RobotMode.IDLE,
            "WORKING": RobotMode.TASKING,
            "MOVING": RobotMode.TASKING,
            "CHARGING": RobotMode.CHARGING,
            "ERROR": RobotMode.ERROR,
            "PAUSED": RobotMode.IDLE,
            "MANUAL": RobotMode.IDLE,
        }
        mode = mode_map.get(sys_status, _parse_vda5050_mode(raw))

        return GeekPlusState(
            robot_id=str(robot_id),
            pose=pose,
            battery_percent=battery,
            mode=mode,
            velocity=float(raw.get("velocity", 0.0)),
            errors=_parse_vda5050_errors(raw),
            sensor_health=SensorHealth(time_sync=HealthStatus.DEGRADED),
            robot_model=raw.get("robotModel", ""),
            warehouse_id=raw.get("warehouseId", ""),
        )

    def to_fleet_state(self, robot_state: GeekPlusState) -> FleetState:
        return FleetState(
            robot_id=robot_state.robot_id,
            boot_id=robot_state.boot_id,
            pose=robot_state.pose,
            battery_percent=robot_state.battery_percent,
            mode=robot_state.mode,
            errors=robot_state.errors,
            sensor_health=robot_state.sensor_health,
            velocity=robot_state.velocity,
            capability=self.to_capability_vector(),
        )

    def to_capability_vector(self) -> CapabilityVector:
        return _capability_from_knowledge("geekplus")

    def extract_errors(self, state: dict) -> list[dict]:
        errs = state.get("errors", []) or []
        # Geek+ may also report in "warnings" and "faults"
        for key in ("warnings", "faults"):
            for w in state.get(key, []) or []:
                errs.append(
                    {"errorType": "WARN", "errorLevel": "WARNING", "errorDescription": str(w)}
                )
        return errs

    def dispatch(self, order: dict) -> dict:
        return {
            "taskId": order.get("orderId", ""),
            "operations": [{"type": "MOVE", "target": n} for n in order.get("path", [])],
        }


class GeekPlusState:
    __slots__ = (
        "robot_id",
        "boot_id",
        "pose",
        "battery_percent",
        "mode",
        "velocity",
        "errors",
        "sensor_health",
        "robot_model",
        "warehouse_id",
    )

    def __init__(
        self,
        robot_id: str,
        pose: Pose,
        battery_percent: float,
        mode: RobotMode,
        velocity: float,
        errors: list[str],
        sensor_health: SensorHealth,
        robot_model: str = "",
        warehouse_id: str = "",
        boot_id: str = "",
    ) -> None:
        self.robot_id = robot_id
        self.boot_id = boot_id
        self.pose = pose
        self.battery_percent = battery_percent
        self.mode = mode
        self.velocity = velocity
        self.errors = errors
        self.sensor_health = sensor_health
        self.robot_model = robot_model
        self.warehouse_id = warehouse_id


# ═══════════════════════════════════════════════════════════════════
#  HaiRobotics Strategy
# ═══════════════════════════════════════════════════════════════════


class HaiRoboticsStrategy:
    """HaiRobotics (海柔创新) HaiPick ACR strategy.

    Quirks:
      - Shelf-to-person robots: carry whole shelf pods.
      - Reports ``robotMode`` + ``taskStatusCode`` alongside VDA5050 fields.
      - ``taskStatusCode``: 0=idle, 1=carrying, 2=waiting, 3=error.
      - Height matters: ACR needs z-coordinate awareness even on a flat floor
        (lift height). Stored as ``fork_height_m`` in the intermediate state.
      - Default origin uses HaiPick coordinate system (x/y swapped vs standard).
    """

    brand = "hairobotics"

    def __init__(self, transformer: MapTransformer | None = None) -> None:
        self._transformer = transformer or MapTransformer.identity("hairobotics")

    def handle_state(self, raw: dict) -> HaiRoboticsState:
        robot_id = raw.get("robotId", raw.get("robot_id", raw.get("deviceId", "hai_unknown")))
        pose = _parse_pose(raw)
        pose = _apply_transform(self._transformer, pose)

        battery_raw = raw.get("batteryState", raw.get("battery", {}))
        battery = _normalise_battery(
            float(battery_raw.get("batteryCharge", battery_raw.get("soc", 100.0)))
        )

        # HaiPick robotMode mapping
        robot_mode = raw.get("robotMode", "").strip().upper()
        task_code = int(raw.get("taskStatusCode", raw.get("taskStatus", 0)))
        if robot_mode == "ERROR" or task_code == 3:
            mode = RobotMode.ERROR
        elif task_code == 1:
            mode = RobotMode.TASKING
        elif task_code == 2:
            mode = RobotMode.IDLE
        else:
            mode = _parse_vda5050_mode(raw)

        return HaiRoboticsState(
            robot_id=str(robot_id),
            pose=pose,
            battery_percent=battery,
            mode=mode,
            velocity=float(raw.get("velocity", 0.0)),
            errors=_parse_vda5050_errors(raw),
            sensor_health=SensorHealth(
                velocity_sensor=HealthStatus.HEALTHY,
                lidar=HealthStatus.DEGRADED,  # ACR uses QR, not lidar
                camera=HealthStatus.HEALTHY,
                time_sync=HealthStatus.HEALTHY,
            ),
            fork_height_m=float(raw.get("forkHeight", raw.get("liftHeight", 0.0))),
        )

    def to_fleet_state(self, robot_state: HaiRoboticsState) -> FleetState:
        return FleetState(
            robot_id=robot_state.robot_id,
            boot_id=robot_state.boot_id,
            pose=robot_state.pose,
            battery_percent=robot_state.battery_percent,
            mode=robot_state.mode,
            errors=robot_state.errors,
            sensor_health=robot_state.sensor_health,
            velocity=robot_state.velocity,
            capability=self.to_capability_vector(),
        )

    def to_capability_vector(self) -> CapabilityVector:
        return _capability_from_knowledge("hairobotics")

    def extract_errors(self, state: dict) -> list[dict]:
        return state.get("errors", []) or []

    def dispatch(self, order: dict) -> dict:
        return {
            "taskId": order.get("orderId", ""),
            "waypoints": order.get("path", []),
            "action": order.get("action", "MOVE"),
        }


class HaiRoboticsState:
    __slots__ = (
        "robot_id",
        "boot_id",
        "pose",
        "battery_percent",
        "mode",
        "velocity",
        "errors",
        "sensor_health",
        "fork_height_m",
    )

    def __init__(
        self,
        robot_id: str,
        pose: Pose,
        battery_percent: float,
        mode: RobotMode,
        velocity: float,
        errors: list[str],
        sensor_health: SensorHealth,
        fork_height_m: float = 0.0,
        boot_id: str = "",
    ) -> None:
        self.robot_id = robot_id
        self.boot_id = boot_id
        self.pose = pose
        self.battery_percent = battery_percent
        self.mode = mode
        self.velocity = velocity
        self.errors = errors
        self.sensor_health = sensor_health
        self.fork_height_m = fork_height_m


# ═══════════════════════════════════════════════════════════════════
#  Quicktron Strategy
# ═══════════════════════════════════════════════════════════════════


class QuicktronStrategy:
    """Quicktron (快仓) QuickBin VDA5050 strategy.

    Quirks:
      - Reports ``robotStatus`` alongside standard VDA5050 fields.
      - Chinese error codes in ``errorCode`` (e.g. "E001" → "激光雷达异常").
        Mapped to v5.0 ERR_* format with the original code preserved.
      - Battery reported in both ``batteryPercent`` and ``batteryVoltage``.
      - ``quickBinStatus``: 0=idle, 1=bin_up, 2=bin_down, 3=error.
    """

    brand = "quicktron"

    # Quicktron error code → human-readable label
    _ERROR_LABELS: dict[str, str] = {
        "E001": "LIDAR_ANOMALY",
        "E002": "MOTOR_FAULT",
        "E003": "BATTERY_LOW",
        "E004": "COMMUNICATION_LOST",
        "E005": "OBSTACLE_DETECTED",
        "E006": "NAVIGATION_FAILURE",
        "E007": "EMERGENCY_STOP",
        "E008": "BIN_MECHANISM_FAULT",
        "E009": "OVER_TEMPERATURE",
        "E010": "POSITION_LOST",
    }

    def __init__(self, transformer: MapTransformer | None = None) -> None:
        self._transformer = transformer or MapTransformer.identity("quicktron")

    def handle_state(self, raw: dict) -> QuicktronState:
        robot_id = raw.get(
            "robotId", raw.get("robot_id", raw.get("serialNumber", "quicktron_unknown"))
        )
        pose = _parse_pose(raw)
        pose = _apply_transform(self._transformer, pose)

        battery_raw = raw.get("batteryState", raw.get("battery", {}))
        battery = _normalise_battery(
            float(battery_raw.get("batteryCharge", raw.get("batteryPercent", 100.0)))
        )

        # Quicktron robotStatus → RobotMode
        status = raw.get("robotStatus", raw.get("operatingMode", "IDLE")).strip().upper()
        qt_mode_map = {
            "IDLE": RobotMode.IDLE,
            "READY": RobotMode.IDLE,
            "RUNNING": RobotMode.TASKING,
            "MOVING": RobotMode.TASKING,
            "CHARGING": RobotMode.CHARGING,
            "ERROR": RobotMode.ERROR,
            "PAUSED": RobotMode.IDLE,
            "DOCKING": RobotMode.TASKING,
        }
        mode = qt_mode_map.get(status, _parse_vda5050_mode(raw))

        errors = _parse_quicktron_errors(raw)

        return QuicktronState(
            robot_id=str(robot_id),
            pose=pose,
            battery_percent=battery,
            mode=mode,
            velocity=float(raw.get("velocity", 0.0)),
            errors=errors,
            sensor_health=SensorHealth(),
            bin_status=int(raw.get("quickBinStatus", 0)),
        )

    def to_fleet_state(self, robot_state: QuicktronState) -> FleetState:
        return FleetState(
            robot_id=robot_state.robot_id,
            boot_id=robot_state.boot_id,
            pose=robot_state.pose,
            battery_percent=robot_state.battery_percent,
            mode=robot_state.mode,
            errors=robot_state.errors,
            sensor_health=robot_state.sensor_health,
            velocity=robot_state.velocity,
            capability=self.to_capability_vector(),
        )

    def to_capability_vector(self) -> CapabilityVector:
        return _capability_from_knowledge("quicktron")

    def extract_errors(self, state: dict) -> list[dict]:
        if "errorCode" in state:
            return [
                {
                    "errorType": "ERROR",
                    "errorLevel": "WARNING",
                    "errorDescription": state["errorCode"],
                }
            ]
        return state.get("errors", []) or []

    def dispatch(self, order: dict) -> dict:
        return {
            "orderId": order.get("orderId", ""),
            "nodes": [
                {"nodeId": n, "sequenceId": i, "released": True}
                for i, n in enumerate(order.get("path", []))
            ],
        }


class QuicktronState:
    __slots__ = (
        "robot_id",
        "boot_id",
        "pose",
        "battery_percent",
        "mode",
        "velocity",
        "errors",
        "sensor_health",
        "bin_status",
    )

    def __init__(
        self,
        robot_id: str,
        pose: Pose,
        battery_percent: float,
        mode: RobotMode,
        velocity: float,
        errors: list[str],
        sensor_health: SensorHealth,
        bin_status: int = 0,
        boot_id: str = "",
    ) -> None:
        self.robot_id = robot_id
        self.boot_id = boot_id
        self.pose = pose
        self.battery_percent = battery_percent
        self.mode = mode
        self.velocity = velocity
        self.errors = errors
        self.sensor_health = sensor_health
        self.bin_status = bin_status


def _parse_quicktron_errors(raw: dict) -> list[str]:
    errors: list[str] = []
    err_code = raw.get("errorCode", "")
    if err_code:
        label = QuicktronStrategy._ERROR_LABELS.get(err_code, err_code)
        errors.append(f"ERR_QT_{label}:{err_code}")
    for e in raw.get("errors", []) or []:
        if isinstance(e, str):
            errors.append(e)
        else:
            errors.append(f"{e.get('errorType', '')}:{e.get('errorDescription', '')}")
    return errors
