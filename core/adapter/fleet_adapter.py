"""Fleet Adapter — the boundary between platform and black-box SCS (v4.0 §5.4).

Per 附录A.5: the Adapter SDK is a 通信框架 + 模板代码, NOT a 万能适配器.
- SDK 封装: DDS通信 / QoS / 心跳保活 / RMF消息格式转换 (this layer)
- 需自行实现: 厂商私有状态机 / 错误码映射 / 坐标系转换 (subclasses)

This base owns:
  - heartbeat keep-alive (灰犀牛 #9)
  - shadow-state reconciliation + 5s behavior-deadline breaker (影子状态机 + 补丁4)
  - hardcoded open-loop retreat (硬编码后退: /cmd_vel 负速度 + 0 角速度, 5 米)
  - SCS negative-velocity capability check → mark lane no_reverse
  - max-speed enforcement (严格执行平台下发的最大线速度)
  - waypoint-order immutability (禁止改 waypoints 顺序或跳过节点)
  - boot_id takeover protocol (灰犀牛 #12 身份漂移)

GitHub: fleet_adapter_template (https://github.com/open-rmf/fleet_adapter_template)
        fleet_adapter_python (https://github.com/open-rmf/fleet_adapter_python)
        rmf_fleet_msgs    (https://github.com/open-rmf/rmf_fleet_msgs)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.adapter.map_transformer import MapTransformer
from core.adapter.shadow_state_machine import ShadowStateMachine
from core.config import LivenessConfig
from core.messages import FleetState, Pose, RobotMode, TaskAssignment
from core.survival.version_router import VersionRouter

RETREAT_METRES = 5.0  # v4.0: 后退 5 米
RETREAT_LINEAR_VEL = -0.2  # 开环负速度 (m/s)
RETREAT_ANGULAR_VEL = 0.0  # 0 角速度


@dataclass
class CmdVel:
    """开环 /cmd_vel 指令 (硬编码后退用)."""

    linear_x: float
    angular_z: float


@dataclass
class AdapterCommand:
    """Fallback / control command emitted by the adapter."""

    robot_id: str
    action: str  # "RETREAT" | "HOLD" | "CHARGE" | "SPEED_CAP"
    reason: str
    cmd_vel: CmdVel | None = None
    metres: float = 0.0
    seq: int = 0
    sent_at: float = 0.0
    retries: int = 0


@dataclass
class AdapterRegistry:
    """Per-robot cached capability + active waypoint contract.

    v4.0 §5.4: 本地自治权必须有边界 — 禁止改 waypoints 顺序或跳过节点.
    """

    supports_reverse: bool = False
    active_path: list[str] = field(default_factory=list)
    next_waypoint_idx: int = 0


class FleetAdapter:
    """Per-brand adapter base. Subclass to add the vendor state machine."""

    ACK_TIMEOUT = 1.0  # seconds before resending an unacked command
    CMD_MAX_RETRIES = 3

    def __init__(
        self,
        brand: str = "generic",
        shadow: ShadowStateMachine | None = None,
        config: LivenessConfig | None = None,
        transformer: MapTransformer | None = None,
        version_router: VersionRouter | None = None,
    ) -> None:
        self.brand = brand
        self.shadow = shadow or ShadowStateMachine()
        self.cfg = config or LivenessConfig()
        self.transformer = transformer or MapTransformer.identity(brand)
        self.version_router = version_router
        self._last_state: dict[str, FleetState] = {}
        self._registry: dict[str, AdapterRegistry] = {}
        self.pending_commands: list[AdapterCommand] = []
        self._unacked: dict[int, AdapterCommand] = {}
        self._cmd_seq = 0

    # ── uplink ingest ──────────────────────────────────────────
    def ingest_native_state(self, raw: dict, now: float) -> tuple[FleetState, list[str]]:
        """Translate a vendor-native state dict into unified FleetState + events.

        If a ``version_router`` is provided, legacy (e.g. v4.x) fields are
        upgraded before vendor mapping. Parse failures are caught and turned
        into an ``ERR_ADAPTER_PARSE`` event instead of crashing the platform loop.
        """
        robot_id = raw.get("robotId", raw.get("robot_id", "unknown"))
        try:
            if self.version_router is not None and "version" in raw:
                from core.survival.version_router import VersionedMessage

                msg = VersionedMessage(version=str(raw["version"]), body=raw)
                raw = self.version_router.normalise(msg).body
            state = self.map_vendor_state(raw)
            events = self.ingest_state(state, now)
            return state, events
        except Exception as exc:  # noqa: BLE001
            event = f"ERR_ADAPTER_PARSE:{self.brand}:{robot_id}:{type(exc).__name__}"
            # minimal synthetic state so the platform loop can keep running
            state = FleetState(
                robot_id=str(robot_id),
                boot_id="",
                pose=Pose(x=0.0, y=0.0, theta=0.0, position_initialized=False),
                battery_percent=0.0,
                mode=RobotMode.ERROR,
                errors=[event],
            )
            return state, [event]

    def ingest_state(self, state: FleetState, now: float) -> list[str]:
        """Receive a unified FleetState; reconcile shadow, detect boot drift."""
        events: list[str] = []
        prev = self._last_state.get(state.robot_id)
        if prev is not None and prev.boot_id != state.boot_id:
            # 灰犀牛 #12: 身份漂移 → 重启接管协议
            events.append(f"BOOT_TAKEOVER:{state.robot_id}")
        self._last_state[state.robot_id] = state
        # cache reverse capability for retreat feasibility
        reg = self._registry.setdefault(state.robot_id, AdapterRegistry())
        reg.supports_reverse = state.capability.supports_reverse
        mm = self.shadow.reconcile(state, now)
        if mm is not None:
            events.append(f"SHADOW_MISMATCH:{state.robot_id}:{mm.expected}->{mm.actual}")
        return events

    def expect(self, robot_id: str, mode: RobotMode) -> None:
        """Platform tells the adapter what state a robot SHOULD be in."""
        self.shadow.expect(robot_id, mode)

    def expect_behavior(self, robot_id: str, mode: RobotMode, now: float) -> None:
        """v4.0 补丁4: 下发指令后, 期望 5s 内看到 mode, 否则熔断."""
        self.shadow.expect_behavior(robot_id, mode, now)

    def tick(self, now: float) -> list[str]:
        """Advance shadow breaker; enqueue retreats for newly-tripped robots;
        resend unacked commands."""
        events: list[str] = []
        for rid in self.shadow.tick(now):
            events.append(f"BREAKER_HALF_OPEN:{rid}")
        while self.shadow.behavior_timeouts:
            rid = self.shadow.behavior_timeouts.popleft()
            events.append(f"BEHAVIOR_TIMEOUT_5S:{rid}")
            self._enqueue_retreat(rid, now)

        # retry / expire unacked commands
        for seq in list(self._unacked):
            cmd = self._unacked.get(seq)
            if cmd is None:
                continue
            if now - cmd.sent_at < self.ACK_TIMEOUT:
                continue
            if cmd.retries >= self.CMD_MAX_RETRIES:
                self._unacked.pop(seq, None)
                events.append(f"CMD_TIMEOUT:{cmd.robot_id}:{cmd.action}:{seq}")
                continue
            cmd.retries += 1
            cmd.sent_at = now
            self.pending_commands.append(cmd)

        return events

    # ── downlink / SCS failure ─────────────────────────────────
    def scs_timeout(self, robot_id: str, now: float) -> bool:
        """Called when the SCS fails to ack. Returns True if tripped."""
        self.shadow.record_scs_timeout(robot_id, now)
        if self.shadow.should_fallback(robot_id):
            self._enqueue_retreat(robot_id, now)
            return True
        return False

    def _enqueue_retreat(self, robot_id: str, now: float = 0.0) -> None:
        """硬编码后退: 开环 /cmd_vel 负速度 + 0 角速度, 后退 5 米."""
        self.request_fallback(robot_id, "breaker_open", now)

    # ── dispatch + speed enforcement + waypoint immutability ────
    def dispatch(
        self, robot_id: str, assignment: TaskAssignment, now: float
    ) -> AdapterCommand | None:
        """Accept a downlink TaskAssignment for ``robot_id``.

        v4.0 §5.4:
          - 严格执行平台下发的最大线速度 (clamp to assignment.max_speed).
          - 禁止改 waypoints 顺序或跳过节点 (active_path locked, idx monotonic).
          - 下发后置 5s 行为期望 (补丁4).
        Returns a fallback command if the breaker is open; else None (SCS handles it).
        """
        if not assignment.path:
            return None
        if self.shadow.should_fallback(robot_id):
            self._enqueue_retreat(robot_id)
            return None
        # lock waypoint contract (immutability)
        reg = self._registry.setdefault(robot_id, AdapterRegistry())
        reg.active_path = list(assignment.path)
        reg.next_waypoint_idx = 0
        # behavior expectation: robot should enter TASKING within 5s
        self.expect_behavior(robot_id, RobotMode.TASKING, now)
        return None  # normal dispatch goes to the vendor-specific subclass

    def advance_waypoint(self, robot_id: str, reached_node: str) -> bool:
        """Waypoint-order immutability: only the *next* node in the locked
        path may be acknowledged. Skipping/reordering is refused."""
        reg = self._registry.get(robot_id)
        if reg is None or not reg.active_path:
            return False
        idx = reg.next_waypoint_idx
        if idx >= len(reg.active_path) or reg.active_path[idx] != reached_node:
            return False  # attempted skip/reorder — refused
        reg.next_waypoint_idx += 1
        return True

    def enforce_speed_limit(self, robot_id: str, commanded: float, max_speed: float) -> float:
        """v4.0 §5.4: 严格执行平台下发的最大线速度限制."""
        return min(commanded, max_speed)

    def mark_no_reverse_lanes(self, fmap) -> list[str]:
        """Lanes the active fleet cannot reverse on (SCS no negative velocity).

        Called by the platform after registration so the nav graph carries
        explicit no_reverse markings (v4.0 §5.4).
        """
        marked: list[str] = []
        for _rid, reg in self._registry.items():
            if not reg.supports_reverse:
                for lane in fmap.all_lanes():
                    if not lane.no_reverse:
                        lane.no_reverse = True
                        marked.append(lane.lane_id)
        return marked

    def current_path(self, robot_id: str) -> tuple[list[str], int]:
        """Return the locked active path and the index of the next expected node."""
        reg = self._registry.get(robot_id)
        if reg is None:
            return [], 0
        return list(reg.active_path), reg.next_waypoint_idx

    # ── vendor extension point ─────────────────────────────────
    def map_vendor_state(self, raw: dict) -> FleetState:
        """subclasses implement: 厂商私有状态机 + 坐标系转换."""
        raise NotImplementedError("subclass must implement map_vendor_state")

    def map_vendor_errors(self, raw_errors: list) -> list[str]:
        """subclasses implement: 错误码映射 (VDA5050 → v5.0 ERR_*)."""
        raise NotImplementedError("subclass must implement map_vendor_errors")

    # ── public fallback trigger (used by coordinator deadlock / safety logic) ─
    def request_speed_cap(
        self, robot_id: str, max_speed: float, reason: str, now: float = 0.0
    ) -> AdapterCommand:
        """Enqueue a SPEED_CAP command for ``robot_id``."""
        return self._issue_command(
            AdapterCommand(robot_id=robot_id, action="SPEED_CAP", reason=reason, metres=max_speed),
            now,
        )

    def request_hold(self, robot_id: str, reason: str, now: float = 0.0) -> AdapterCommand:
        """Enqueue a non-retreat HOLD command for ``robot_id``."""
        return self._issue_command(
            AdapterCommand(robot_id=robot_id, action="HOLD", reason=reason), now
        )

    def request_fallback(self, robot_id: str, reason: str, now: float = 0.0) -> AdapterCommand:
        """Enqueue a retreat or hold for ``robot_id`` if conditions require."""
        reg = self._registry.get(robot_id)
        if reg is not None and not reg.supports_reverse:
            return self._issue_command(AdapterCommand(robot_id, "HOLD", "no_reverse_support"), now)
        return self._issue_command(
            AdapterCommand(
                robot_id=robot_id,
                action="RETREAT",
                reason=reason,
                cmd_vel=CmdVel(linear_x=RETREAT_LINEAR_VEL, angular_z=RETREAT_ANGULAR_VEL),
                metres=RETREAT_METRES,
            ),
            now,
        )

    def _issue_command(self, cmd: AdapterCommand, now: float) -> AdapterCommand:
        self._cmd_seq += 1
        cmd.seq = self._cmd_seq
        cmd.sent_at = now
        self.pending_commands.append(cmd)
        self._unacked[cmd.seq] = cmd
        return cmd

    def ack_command(self, seq: int) -> bool:
        """SCS acknowledges command ``seq``; return True if it was pending."""
        return self._unacked.pop(seq, None) is not None

    def clear_pending_holds(self, robot_id: str) -> None:
        """Drop all unacked HOLD commands for *robot_id*.

        Called when the condition that triggered the HOLD no longer applies
        (e.g. traffic light turned green) so stale retries don't keep the
        robot frozen.
        """
        for seq in list(self._unacked):
            cmd = self._unacked[seq]
            if cmd.robot_id == robot_id and cmd.action == "HOLD":
                self._unacked.pop(seq, None)
        self.pending_commands = [
            c for c in self.pending_commands if not (c.robot_id == robot_id and c.action == "HOLD")
        ]
