"""Robot Platform Coordinator — one map, one order queue, one platform loop.

This is the integration heart of the v5.0 core. It wires together:

- ``FixedLaneMap`` (unified lane graph)
- ``TrafficLightController`` (intersection ordering)
- ``TaskAllocator`` + ``OrderSequencer`` (order → robot assignment)
- ``RobotAsObstacle`` + ``SafeDistanceCalculator`` (multi-brand collision avoidance)
- ``FailoverDegrade`` (liveness + degraded mode)
- ``FacilityManager``, ``ChargerReservation``, ``LiftManager`` (shared resources)
- ``ReputationEngine`` + ``EconomicModel`` (governance)
- ``WormBlackbox`` (audit chain)
- ``FleetAdapter`` registry (one per brand)

The coordinator is intentionally transport-agnostic: it consumes unified
``FleetState`` objects and emits ``TaskAssignment`` / ``AdapterCommand``
objects.  The HTTP/MQTT/DDS gateway sits outside and calls
``ingest_uplink`` / ``tick``.
"""
from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.adapter.fleet_adapter import AdapterCommand, FleetAdapter
from core.config import CoreConfig
from core.governance.economic_model import EconomicModel
from core.governance.reputation_engine import ReputationEngine
from core.messages import ActionPrimitive, FleetState, RobotMode, TaskAssignment
from core.observability import CoreMetrics, MetricsSnapshot
from core.orders import Order, OrderPlan, OrderSequencer, OrderStatus
from core.platform.charger_reservation import ChargerReservation
from core.platform.failover_degrade import FailoverDegrade
from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.platform.lift_manager import LiftManager
from core.platform.robot_as_obstacle import RobotAsObstacle
from core.safety.safe_distance import SafeDistanceCalculator
from core.scheduling.facility_manager import FacilityManager
from core.scheduling.task_allocator import Task, TaskAllocator, model_of
from core.scheduling.traffic_light_controller import TrafficLightController
from core.survival.version_router import VersionRouter
from core.survival.worm_blackbox import WormBlackbox

logger = logging.getLogger(__name__)


@dataclass
class TickResult:
    """Output of one coordinator tick."""

    events: list[str] = field(default_factory=list)
    assignments: list[tuple[str, TaskAssignment]] = field(default_factory=list)
    commands: list[AdapterCommand] = field(default_factory=list)
    deadlocks: list[str] = field(default_factory=list)
    transitions: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class PlatformState:
    """Snapshot for dashboards / API queries."""

    robots: dict[str, FleetState] = field(default_factory=dict)
    locked_zones: list[str] = field(default_factory=list)
    pending_tasks: int = 0
    active_assignments: int = 0
    pending_commands: int = 0
    metrics: MetricsSnapshot = field(default_factory=MetricsSnapshot)


class RobotPlatformCoordinator:
    """Single platform loop for heterogeneous robot fleets."""

    def __init__(
        self,
        config: CoreConfig | None = None,
        fmap: FixedLaneMap | None = None,
        traffic: TrafficLightController | None = None,
        allocator: TaskAllocator | None = None,
        reputation: ReputationEngine | None = None,
        economic: EconomicModel | None = None,
        failover: FailoverDegrade | None = None,
        obstacles: RobotAsObstacle | None = None,
        facility: FacilityManager | None = None,
        charger: ChargerReservation | None = None,
        lift: LiftManager | None = None,
        worm: WormBlackbox | None = None,
        version_router: VersionRouter | None = None,
        sequencer: OrderSequencer | None = None,
        metrics: CoreMetrics | None = None,
    ) -> None:
        self.cfg = config or CoreConfig()
        self.fmap = fmap or FixedLaneMap()
        self.traffic = traffic or TrafficLightController()
        self.reputation = reputation or ReputationEngine(self.cfg.governance)
        self.economic = economic or EconomicModel(self.reputation, self.cfg.governance)
        self.failover = failover or FailoverDegrade(self.cfg.liveness)
        self.safe_distance = SafeDistanceCalculator(self.cfg.safety)
        self.obstacles = obstacles or RobotAsObstacle(self.fmap, self.safe_distance)
        self.facility = facility or FacilityManager()
        self.charger = charger or ChargerReservation(self.cfg.charger)
        self.lift = lift or LiftManager()
        self.worm = worm or WormBlackbox(
            self.cfg.worm,
            sink_path=Path(self.cfg.worm.sink_dir) / "worm.jsonl",
        )
        self.version_router = version_router or VersionRouter(self.cfg)
        self.sequencer = sequencer or OrderSequencer(self.fmap)
        self.metrics = metrics or CoreMetrics()

        # Build allocator after economic model so it can apply γ cost term.
        self.allocator = allocator or TaskAllocator(
            self.reputation,
            self.cfg.governance,
            self.economic,
            distance_fn=self.fmap.distance_between,
            lane_lookup=self.fmap.lane,
        )

        self._adapters: dict[str, FleetAdapter] = {}
        self._robot_adapter: dict[str, FleetAdapter] = {}
        self._robot_states: dict[str, FleetState] = {}
        self._task_queue: deque[Task] = deque()
        self._order_plans: dict[str, OrderPlan] = {}
        self._task_order: dict[str, str] = {}
        self._order_completion: dict[str, set[str]] = {}
        self._task_retries: dict[str, int] = {}
        self._active_assignments: dict[str, TaskAssignment] = {}
        self._robot_lane: dict[str, str] = {}  # robot_id -> current lane

    MAX_TASK_RETRIES = 3

    # ── adapter / brand registry ─────────────────────────────────
    def register_adapter(self, adapter: FleetAdapter) -> None:
        """Register one fleet adapter per brand."""
        if adapter.brand in self._adapters:
            raise ValueError(f"adapter for brand {adapter.brand!r} already registered")
        self._adapters[adapter.brand] = adapter

    def adapter_for(self, robot_id: str) -> FleetAdapter | None:
        return self._robot_adapter.get(robot_id)

    # ── uplink ingestion ─────────────────────────────────────────
    def ingest_uplink(self, brand: str, raw: dict, now: float) -> list[str]:
        """Ingest one vendor-native state update and return platform events."""
        self.metrics.inc("uplinks")
        adapter = self._adapters.get(brand)
        if adapter is None:
            self._worm_event(now, "ERROR", raw.get("robotId", "?"), {"reason": "unknown_brand", "brand": brand})
            return [f"ERR_UNKNOWN_BRAND:{brand}"]

        state, events = adapter.ingest_native_state(raw, now)
        if any("ERR_ADAPTER_PARSE" in e for e in events):
            self.metrics.inc("adapter_parse_errors")
        self._robot_adapter[state.robot_id] = adapter

        # failover observes liveness and stamps platform-maintained flags
        events.extend(self.failover.observe(state, now))
        state = self.failover.stamp(state)
        self._robot_states[state.robot_id] = state
        self._auto_report_progress(state.robot_id, now)

        # footprint / obstacle layer update
        self.obstacles.update(
            robot_id=state.robot_id,
            x=state.pose.x,
            y=state.pose.y,
            theta=state.pose.theta,
            velocity=state.velocity,
            rtt=0.1,  # default until RTT is measured by gateway
        )

        for ev in events:
            if ev.startswith("ERR_") or "BOOT_TAKEOVER" in ev or "SHADOW_MISMATCH" in ev:
                self._worm_event(now, "ERROR", state.robot_id, {"event": ev})
        return events

    # ── order intake ─────────────────────────────────────────────
    def submit_order(self, order: Order) -> OrderPlan:
        """Enqueue a WMS/ERP order; returns the planned task sequence."""
        self.metrics.inc("orders_submitted")
        plan = self.sequencer.plan(order)
        self._order_plans[order.order_id] = plan
        self._order_completion[order.order_id] = set()
        for task in plan.tasks:
            self._task_queue.append(task)
            self._task_order[task.task_id] = order.order_id
            self._task_retries[task.task_id] = 0
        return plan

    # ── main loop ────────────────────────────────────────────────
    def tick(self, now: float) -> TickResult:
        """Advance one platform tick: safety, traffic, allocation, resources."""
        result = TickResult()

        # 1. liveness + failover
        transitions = self.failover.tick(now)
        result.transitions.extend(transitions)
        for rid, trans in transitions:
            self._worm_event(now, "EVENT", rid, {"transition": trans})

        # 2. traffic lights + deadlock detection
        self.traffic.tick(now)
        for br in self.traffic.detect_deadlocks(now):
            result.deadlocks.append(br.retreat_robot_id)
            self.metrics.inc("deadlocks")
            self.reputation.record_violation(br.retreat_robot_id, now, reason="deadlock")
            adapter = self.adapter_for(br.retreat_robot_id)
            if adapter is not None:
                cmd = adapter.request_fallback(br.retreat_robot_id, "deadlock_break", now)
                if cmd:
                    result.commands.append(cmd)
            self._worm_event(
                now, "ERROR", br.retreat_robot_id,
                {"deadlock": br.intersection_id, "direction": br.direction},
            )

        # 3. shared resources
        self.charger.tick(now)
        self.lift.tick(now)
        for zone_id, rid in self.facility.reap_zombies(now, self.cfg.liveness.zombie_hold_seconds):
            self._worm_event(now, "EVENT", rid, {"zombie_reap": zone_id})

        # 3.5 collision enforcement across all brand footprints
        self._enforce_collisions(now, result)

        # 3.6 reconcile active assignments with robot health
        self._reap_offline_assignments(now)

        # 3.7 intersection traffic-light gating
        self._gate_intersections(now, result)

        # 3.8 safe-distance speed advisories
        self._compute_safe_speed_advisories(now, result)

        # 3.9 automatic low-battery charger dispatch
        self._ensure_charging(now)

        # 4. traffic demand based on active paths
        self._update_traffic_demand(now)

        # 5. task allocation from the unified queue
        result.assignments.extend(self._dispatch_pending_tasks(now))

        # 6. collect any adapter-level fallback commands (SCS timeouts, behavior timeouts)
        for adapter in self._adapters.values():
            events = adapter.tick(now)
            result.events.extend(events)
            result.commands.extend(adapter.pending_commands)
            adapter.pending_commands.clear()

        return result

    def _dispatch_pending_tasks(self, now: float) -> list[tuple[str, TaskAssignment]]:
        """Try to allocate and dispatch tasks in priority order."""
        assigned: list[tuple[str, TaskAssignment]] = []
        remaining: deque[Task] = deque()

        # highest priority first; older tasks break ties to avoid starvation
        tasks = sorted(self._task_queue, key=lambda t: (-t.priority, t.created_at))
        self._task_queue.clear()

        # Track robots assigned during *this* tick to prevent double-assignment
        # before _active_assignments is updated (which happens after successful dispatch).
        assigned_robots: set[str] = set()
        for task in tasks:
            if self._is_expired_or_exhausted(task, now):
                continue

            candidates = [
                r for r in self._robot_states.values()
                if r.robot_id not in assigned_robots
                and r.robot_id not in self._active_assignments
                and not r.degraded
                and not self.failover.is_offline(r.robot_id)
                and self.failover.accepts_new_tasks(r.robot_id, now)
                and self._breaker_closed(r.robot_id)
                and self._intersection_clear(r.robot_id)
            ]
            result = self.allocator.allocate(task, candidates)
            if not result.assigned:
                if self._requeue_task(task, now, result.reason):
                    remaining.append(task)
                continue

            robot = self._robot_states.get(result.robot_id or "")
            if robot is None:
                if self._requeue_task(task, now, "robot_vanished"):
                    remaining.append(task)
                continue

            adapter = self.adapter_for(robot.robot_id)
            if adapter is None:
                if self._requeue_task(task, now, "no_adapter"):
                    remaining.append(task)
                continue

            # do not hand a new task to a robot whose breaker is open
            if adapter.shadow.should_fallback(robot.robot_id):
                if self._requeue_task(task, now, "breaker_open"):
                    remaining.append(task)
                continue

            assignment = self._build_assignment(robot, task)
            if not self._reserve_lifts_for_assignment(robot, assignment, now):
                if self._requeue_task(task, now, "lift_unavailable"):
                    remaining.append(task)
                continue

            try:
                adapter.dispatch(robot.robot_id, assignment, now)
            except Exception as exc:
                logger.error(
                    "dispatch failed for robot %s task %s: %s",
                    robot.robot_id, task.task_id, exc,
                )
                if self._requeue_task(task, now, "dispatch_exception"):
                    remaining.append(task)
                continue
            self._active_assignments[robot.robot_id] = assignment
            assigned_robots.add(robot.robot_id)
            self._update_occupancy(robot.robot_id, assignment.path[0])
            assigned.append((robot.robot_id, assignment))
            self.metrics.inc("tasks_allocated")
            self._mark_order_executing(task.task_id)
            self.reputation.record_good(robot.robot_id, now, reason="task_assigned")
            self._worm_event(
                now, "EVENT", robot.robot_id,
                {"task_id": task.task_id, "path": assignment.path},
            )

        self._task_queue = remaining
        return assigned

    def _is_expired_or_exhausted(self, task: Task, now: float) -> bool:
        """Drop tasks past deadline or exceeding retry limit."""
        retries = self._task_retries.get(task.task_id, 0)
        if retries >= self.MAX_TASK_RETRIES:
            self._fail_task(task, now, "max_retries")
            return True
        if task.deadline > 0 and now > task.deadline:
            self._fail_task(task, now, "deadline_exceeded")
            return True
        return False

    def _requeue_task(self, task: Task, now: float, reason: str) -> bool:
        """Increment retry count; return True if the task may be requeued."""
        retries = self._task_retries.get(task.task_id, 0) + 1
        self._task_retries[task.task_id] = retries
        if retries >= self.MAX_TASK_RETRIES:
            self._fail_task(task, now, reason)
            return False
        self._worm_event(
            now, "EVENT", task.task_id,
            {"action": "requeue", "reason": reason, "retry": retries},
        )
        return True

    def _fail_task(self, task: Task, now: float, reason: str) -> None:
        """Mark the task and its order as failed."""
        order_id = self._task_order.get(task.task_id)
        if order_id is not None:
            plan = self._order_plans.get(order_id)
            if plan is not None:
                plan.order.status = OrderStatus.FAILED
        self._worm_event(
            now, "ERROR", task.task_id,
            {"action": "task_failed", "reason": reason},
        )

    def _mark_order_executing(self, task_id: str) -> None:
        order_id = self._task_order.get(task_id)
        if order_id is None:
            return
        plan = self._order_plans.get(order_id)
        if plan is not None and plan.order.status is OrderStatus.PLANNED:
            plan.order.status = OrderStatus.EXECUTING

    def _mark_order_completed(self, task_id: str) -> None:
        order_id = self._task_order.get(task_id)
        if order_id is None:
            return
        completed = self._order_completion.setdefault(order_id, set())
        completed.add(task_id)
        plan = self._order_plans.get(order_id)
        if plan is None:
            return
        if completed.issuperset(t.task_id for t in plan.tasks):
            plan.order.status = OrderStatus.COMPLETED

    def _reserve_lifts_for_assignment(
        self, robot: FleetState, assignment: TaskAssignment, now: float
    ) -> bool:
        """Reserve the first lift encountered on the assignment path."""
        for lane_id in assignment.path:
            lane = self.fmap.lane(lane_id)
            if lane is None or lane.lift_id is None or lane.floor is None:
                continue
            # already reserved to this robot?
            if self.lift.current_user(lane.lift_id) == robot.robot_id:
                continue
            if not self.lift.request(lane.lift_id, robot.robot_id, lane.floor, now):
                return False
        return True

    def _breaker_closed(self, robot_id: str) -> bool:
        adapter = self.adapter_for(robot_id)
        return adapter is None or not adapter.shadow.should_fallback(robot_id)

    def _intersection_clear(self, robot_id: str) -> bool:
        """Return False if the robot is already held at a red intersection."""
        adapter = self.adapter_for(robot_id)
        if adapter is None:
            return True
        path, idx = adapter.current_path(robot_id)
        if idx >= len(path):
            return True
        lane = self.fmap.lane(path[idx])
        if lane is None or lane.intersection_id is None:
            return True
        return self.traffic.may_enter(lane.intersection_id, lane.direction)

    def _ensure_charging(self, now: float) -> None:
        """Inject high-priority charge tasks for robots below the force-lock threshold."""
        charger_lanes = self.fmap.chargers()
        if not charger_lanes:
            return
        for robot in self._robot_states.values():
            if robot.mode is RobotMode.CHARGING:
                continue
            if robot.battery_percent > self.charger.cfg.force_lock_threshold:
                continue
            if robot.robot_id in self._active_assignments:
                # already busy; do not pre-empt existing mission
                continue
            if any(t.task_id == f"charge:{robot.robot_id}" for t in self._task_queue):
                continue
            # find nearest reachable charger lane respecting robot capability
            cap = robot.capability
            models = cap.supported_models or [model_of(robot)]

            def _filter(lane: Lane) -> bool:
                return (
                    lane.allows_any(models)
                    and cap.can_traverse(lane.env)
                    and (cap.supports_reverse or not lane.no_reverse)
                    and self.fmap.is_traversable(lane.lane_id)
                )

            reachable = [
                (self.fmap.distance_between(robot.pose.last_node_id, cl, lane_filter=_filter, cost="time"), cl)
                for cl in charger_lanes
            ]
            if not reachable:
                continue
            best = min(reachable, key=lambda x: x[0])
            if best[0] == float("inf"):
                continue
            bay = self.charger.reserve(robot.robot_id, robot.battery_percent, now)
            if bay is None:
                continue
            task = Task(
                task_id=f"charge:{robot.robot_id}",
                start_lane=robot.pose.last_node_id,
                end_lane=best[1],
                priority=100,  # highest
                action_primitives={ActionPrimitive.CHARGE},
            )
            self._task_queue.appendleft(task)
            self._worm_event(
                now, "EVENT", robot.robot_id,
                {"action": "charger_dispatched", "bay": bay, "lane": best[1]},
            )

    def _gate_intersections(self, now: float, result: TickResult) -> None:
        """HOLD robots whose next expected lane is a red intersection."""
        for robot_id, assignment in self._active_assignments.items():
            adapter = self.adapter_for(robot_id)
            if adapter is None:
                continue
            path, idx = adapter.current_path(robot_id)
            if idx >= len(path):
                continue
            next_lane_id = path[idx]
            lane = self.fmap.lane(next_lane_id)
            if lane is None or lane.intersection_id is None:
                continue
            if self.traffic.may_enter(lane.intersection_id, lane.direction):
                continue
            cmd = adapter.request_hold(robot_id, f"red_intersection:{lane.intersection_id}", now)
            result.commands.append(cmd)
            result.events.append(f"INTERSECTION_HOLD:{robot_id}:{lane.intersection_id}")
            self._worm_event(
                now, "EVENT", robot_id,
                {"intersection_id": lane.intersection_id, "direction": lane.direction, "action": "hold"},
            )

    def _compute_safe_speed_advisories(self, now: float, result: TickResult) -> None:
        """Issue SPEED_CAP commands when a robot is too close to one ahead."""
        states = list(self._robot_states.values())
        for i, a in enumerate(states):
            if a.mode not in (RobotMode.IDLE, RobotMode.TASKING):
                continue
            for b in states[i + 1 :]:
                if b.mode not in (RobotMode.IDLE, RobotMode.TASKING):
                    continue
                dx, dy = b.pose.x - a.pose.x, b.pose.y - a.pose.y
                dist = math.hypot(dx, dy)
                if dist == 0:
                    continue
                # is b ahead of a (within ±90° of a's heading)?
                heading_x, heading_y = math.cos(a.pose.theta), math.sin(a.pose.theta)
                if heading_x * dx + heading_y * dy <= 0:
                    continue
                required = self.safe_distance.compute(a.velocity, rtt=0.1, sensor_health=a.sensor_health).applied
                if dist < required:
                    cap = self.safe_distance.speed_cap_for_gap(
                        a.velocity, rtt=0.1, available_gap=dist, sensor_health=a.sensor_health
                    )
                    adapter = self.adapter_for(a.robot_id)
                    if adapter is not None:
                        cmd = adapter.request_speed_cap(
                            a.robot_id, cap, f"safe_distance:{b.robot_id}", now
                        )
                        result.commands.append(cmd)
                        result.events.append(
                            f"SPEED_CAP:{a.robot_id}:{cap:.2f}:gap={dist:.2f}:req={required:.2f}"
                        )
                        self._worm_event(
                            now, "EVENT", a.robot_id,
                            {"ahead_robot": b.robot_id, "gap": dist, "cap": cap},
                        )

    def _update_traffic_demand(self, now: float) -> None:
        """Tell traffic lights which robots are approaching which intersection."""
        for robot_id, assignment in self._active_assignments.items():
            adapter = self.adapter_for(robot_id)
            if adapter is None:
                continue
            path, idx = adapter.current_path(robot_id)
            # look ahead from next expected node for the next intersection lane
            for lane_id in path[idx:]:
                lane = self.fmap.lane(lane_id)
                if lane is not None and lane.intersection_id:
                    self.traffic.report_waiting_robot(
                        lane.intersection_id,
                        robot_id,
                        direction=lane.direction,
                        priority=0,
                        now=now,
                    )
                    break

    def _reap_offline_assignments(self, now: float) -> None:
        """Requeue tasks assigned to robots that went degraded/offline."""
        for robot_id in list(self._active_assignments):
            robot = self._robot_states.get(robot_id)
            if robot is None or robot.degraded or self.failover.is_offline(robot_id):
                assignment = self._active_assignments.pop(robot_id)
                task = Task(
                    task_id=assignment.task_id,
                    start_lane=assignment.path[0],
                    end_lane=assignment.path[-1],
                )
                if self._requeue_task(task, now, "robot_unavailable"):
                    self._task_queue.appendleft(task)
                self.metrics.inc("tasks_requeued")

    def _enforce_collisions(self, now: float, result: TickResult) -> None:
        """Issue HOLD commands for any pair of overlapping footprints."""
        for a, b in self.obstacles.overlapping_pairs():
            for rid in (a, b):
                adapter = self.adapter_for(rid)
                if adapter is not None:
                    cmd = adapter.request_hold(rid, f"collision_with:{a if rid != a else b}", now)
                    result.commands.append(cmd)
            event = f"COLLISION_HOLD:{a},{b}"
            result.events.append(event)
            self.metrics.inc("collision_holds")
            self.reputation.record_violation(a, now, reason="collision")
            self.reputation.record_violation(b, now, reason="collision")
            self._worm_event(now, "ERROR", a, {"collision_with": b})
            self._worm_event(now, "ERROR", b, {"collision_with": a})

    def _build_assignment(self, robot: FleetState, task: Task) -> TaskAssignment:
        """Resolve a robot-specific route and clamp speed."""
        cap = robot.capability
        models = cap.supported_models or [model_of(robot)]

        def _lane_filter(lane: Lane) -> bool:
            if not self.fmap.is_traversable(lane.lane_id):
                return False
            if not lane.allows_any(models):
                return False
            if not cap.can_traverse(lane.env):
                return False
            if not cap.supports_reverse and lane.no_reverse:
                # a robot that cannot reverse should not be routed onto a
                # no_reverse lane because it could not recover from an overshoot
                return False
            return True

        path = self.fmap.shortest_path(task.start_lane, task.end_lane, lane_filter=_lane_filter, cost="time")
        if not path:
            path = [task.start_lane, task.end_lane]

        max_speed = cap.max_speed
        for lane_id in path:
            lane = self.fmap.lane(lane_id)
            if lane is not None:
                max_speed = min(max_speed, lane.max_speed)

        # degraded robots are additionally capped by the platform degrade limit
        degraded_cap = self.failover.degraded_speed_cap(robot.robot_id)
        if degraded_cap is not None:
            max_speed = min(max_speed, degraded_cap)

        return TaskAssignment(
            task_id=task.task_id,
            path=path,
            max_speed=max_speed,
        )

    def block_lane(self, lane_id: str, now: float) -> None:
        """Block a lane and re-route active assignments that used it."""
        self.fmap.block_lane(lane_id)
        self._worm_event(now, "EVENT", "PLATFORM", {"lane_blocked": lane_id})
        for robot_id in list(self._active_assignments):
            assignment = self._active_assignments[robot_id]
            if lane_id not in assignment.path:
                continue
            robot = self._robot_states.get(robot_id)
            if robot is None:
                continue
            # try to re-route from current position to original goal
            task = Task(
                task_id=assignment.task_id,
                start_lane=assignment.path[0],
                end_lane=assignment.path[-1],
            )
            new_assignment = self._build_assignment(robot, task)
            if lane_id in new_assignment.path or new_assignment.path == [task.start_lane, task.end_lane]:
                # no viable alternate route → requeue
                del self._active_assignments[robot_id]
                if self._requeue_task(task, now, "lane_blocked"):
                    self._task_queue.appendleft(task)
                self.metrics.inc("tasks_requeued")
            else:
                self._active_assignments[robot_id] = new_assignment
                adapter = self.adapter_for(robot_id)
                if adapter is not None:
                    adapter.dispatch(robot_id, new_assignment, now)
                self._worm_event(
                    now, "EVENT", robot_id,
                    {"task_id": task.task_id, "status": "rerouted", "new_path": new_assignment.path},
                )

    def unblock_lane(self, lane_id: str, now: float) -> None:
        self.fmap.unblock_lane(lane_id)
        self._worm_event(now, "EVENT", "PLATFORM", {"lane_unblocked": lane_id})

    def cancel_order(self, order_id: str, now: float) -> bool:
        """Cancel a pending or active order and HOLD any robot executing it."""
        plan = self._order_plans.pop(order_id, None)
        if plan is None:
            return False
        plan.order.status = OrderStatus.FAILED
        # remove pending tasks for this order
        self._task_queue = deque(t for t in self._task_queue if self._task_order.get(t.task_id) != order_id)
        # stop active assignments belonging to this order
        task_ids = {t.task_id for t in plan.tasks}
        for robot_id in list(self._active_assignments):
            if self._active_assignments[robot_id].task_id in task_ids:
                del self._active_assignments[robot_id]
                adapter = self.adapter_for(robot_id)
                if adapter is not None:
                    adapter.request_hold(robot_id, "order_cancelled", now)
                self._worm_event(now, "MANUAL", robot_id, {"action": "cancel_order", "order_id": order_id})
        # cleanup mapping
        for task_id in task_ids:
            self._task_order.pop(task_id, None)
        return True

    # ── emergency / manual ops ───────────────────────────────────
    def emergency_stop(self, zone_id: str | None, now: float) -> None:
        """SOP-RED: lock a zone and force all traffic lights red."""
        if zone_id:
            self.facility.lockdown(zone_id, now)
        for it in self.traffic.all_intersections():
            self.traffic.force_all_red(it.intersection_id)
        self._worm_event(now, "ESTOP", "PLATFORM", {"zone": zone_id})

    def manual_recover(self, robot_id: str, now: float) -> None:
        """Operator clears degraded mode and breaker for a robot."""
        self.failover.manual_recover(robot_id)
        adapter = self.adapter_for(robot_id)
        if adapter is not None:
            adapter.shadow.record_success(robot_id)
        self._worm_event(now, "MANUAL", robot_id, {"action": "recover"})

    def _update_occupancy(self, robot_id: str, lane_id: str) -> None:
        """Move robot occupancy to ``lane_id``."""
        prev = self._robot_lane.get(robot_id)
        if prev is not None:
            self.fmap.vacate_lane(prev, robot_id)
        self.fmap.occupy_lane(lane_id, robot_id)
        self._robot_lane[robot_id] = lane_id

    def _auto_report_progress(self, robot_id: str, now: float) -> None:
        """Infer waypoint progress from MQTT/VDA5050 pose alone.

        When a robot's ``pose.last_node_id`` matches the end node of the next
        expected lane in its active assignment, advance the waypoint contract
        and occupancy just as if an explicit HTTP ``/robot/{id}/progress`` had
        been received. This lets protocol-level simulators (and real VDA5050
        robots reporting only state) complete tasks without a separate progress
        channel.
        """
        assignment = self._active_assignments.get(robot_id)
        if assignment is None:
            return
        adapter = self.adapter_for(robot_id)
        if adapter is None:
            return
        state = self._robot_states.get(robot_id)
        if state is None:
            return
        last_node = state.pose.last_node_id
        if not last_node:
            return

        path, idx = adapter.current_path(robot_id)
        for lane_id in path[idx:]:
            lane = self.fmap.lane(lane_id)
            if lane is None:
                break
            if lane.to_node == last_node:
                # Found the lane the robot just completed.
                # Only process one lane per tick — if the robot traversed
                # multiple nodes since the last tick, subsequent ticks will
                # catch up.
                self.report_progress(robot_id, lane_id, now)
                break
            # Robot hasn't reached the end of this lane yet
            break

    def report_progress(self, robot_id: str, reached_lane: str, now: float) -> bool:
        """Report a reached waypoint; returns True if the active assignment is complete."""
        adapter = self.adapter_for(robot_id)
        if adapter is None:
            return False
        advanced = adapter.advance_waypoint(robot_id, reached_lane)
        if not advanced:
            return False

        self._update_occupancy(robot_id, reached_lane)

        # release any lift that was just exited
        path, idx = adapter.current_path(robot_id)
        if idx >= 2:
            prev_lane = self.fmap.lane(path[idx - 2])
            if prev_lane is not None and prev_lane.lift_id:
                self.lift.release(prev_lane.lift_id, robot_id)

        assignment = self._active_assignments.get(robot_id)
        if assignment is None:
            return False
        if reached_lane == assignment.path[-1]:
            del self._active_assignments[robot_id]
            adapter.expect(robot_id, RobotMode.IDLE)
            self.metrics.inc("tasks_completed")
            self._mark_order_completed(assignment.task_id)
            self.reputation.record_good(robot_id, now, reason="task_completed")
            self._worm_event(now, "EVENT", robot_id, {"task_id": assignment.task_id, "status": "completed"})
            return True
        return False

    # ── queries ──────────────────────────────────────────────────
    def query_state(self) -> PlatformState:
        return PlatformState(
            robots=dict(self._robot_states),
            locked_zones=self.facility.locked_zones(),
            pending_tasks=len(self._task_queue),
            active_assignments=len(self._active_assignments),
            pending_commands=sum(len(a.pending_commands) for a in self._adapters.values()),
            metrics=self.metrics.snapshot(),
        )

    # ── state persistence ────────────────────────────────────────
    def snapshot(self) -> dict:
        """Serialize coordinator state for persistence/restart recovery.

        Returns a JSON-serializable dict capturing robots, assignments,
        task queue, and order plans. Adapters are NOT serialized (they
        are rebuilt by bootstrap on restart).
        """
        def _fleet_state_dict(fs: FleetState) -> dict:
            return {
                "robot_id": fs.robot_id,
                "boot_id": fs.boot_id,
                "pose": asdict(fs.pose),
                "battery_percent": fs.battery_percent,
                "mode": int(fs.mode),
                "errors": list(fs.errors),
                "sensor_health": {
                    "velocity_sensor": int(fs.sensor_health.velocity_sensor),
                    "lidar": int(fs.sensor_health.lidar),
                    "camera": int(fs.sensor_health.camera),
                    "time_sync": int(fs.sensor_health.time_sync),
                },
                "velocity": fs.velocity,
                "last_seen_monotonic": fs.last_seen_monotonic,
                "capability": {
                    "payload_kg": fs.capability.payload_kg,
                    "max_speed": fs.capability.max_speed,
                    "supported_models": list(fs.capability.supported_models),
                    "action_primitives": [int(a) for a in fs.capability.action_primitives],
                    "env": asdict(fs.capability.env),
                    "supports_reverse": fs.capability.supports_reverse,
                },
                "degraded": fs.degraded,
                "version": fs.version,
            }

        return {
            "robot_states": {rid: _fleet_state_dict(fs) for rid, fs in self._robot_states.items()},
            "active_assignments": {
                rid: {
                    "task_id": a.task_id,
                    "path": list(a.path),
                    "max_speed": a.max_speed,
                    "version": a.version,
                }
                for rid, a in self._active_assignments.items()
            },
            "task_queue": [
                {
                    "task_id": t.task_id,
                    "start_lane": t.start_lane,
                    "end_lane": t.end_lane,
                    "priority": t.priority,
                    "created_at": t.created_at,
                    "deadline": t.deadline,
                    "action_primitives": [int(a) for a in t.action_primitives],
                    "required_payload_kg": t.required_payload_kg,
                }
                for t in self._task_queue
            ],
            "order_plans": {
                oid: {
                    "order": {
                        "order_id": p.order.order_id,
                        "origin_lane": p.order.origin_lane,
                        "destination_lane": p.order.destination_lane,
                        "actions": [int(a) for a in p.order.actions],
                        "payload_kg": p.order.payload_kg,
                        "priority": p.order.priority,
                        "status": p.order.status.name,
                    },
                    "tasks": [
                        {
                            "task_id": t.task_id,
                            "start_lane": t.start_lane,
                            "end_lane": t.end_lane,
                            "priority": t.priority,
                            "created_at": t.created_at,
                            "deadline": t.deadline,
                            "action_primitives": [int(a) for a in t.action_primitives],
                            "required_payload_kg": t.required_payload_kg,
                        }
                        for t in p.tasks
                    ],
                }
                for oid, p in self._order_plans.items()
            },
            "task_order": dict(self._task_order),
            "order_completion": {oid: list(s) for oid, s in self._order_completion.items()},
            "task_retries": dict(self._task_retries),
            "robot_lane": dict(self._robot_lane),
            "robot_brands": {
                rid: adapter.brand for rid, adapter in self._robot_adapter.items()
            },
        }

    def restore(self, data: dict) -> None:
        """Restore coordinator state from a snapshot dict.

        Adapters must be re-registered via ``register_adapter`` before
        calling this method so that ``_robot_adapter`` mappings can be
        reconstructed from robot states.
        """
        from core.messages import (
            ActionPrimitive,
            CapabilityVector,
            EnvConstraints,
            FleetState,
            HealthStatus,
            Pose,
            RobotMode,
            SensorHealth,
            TaskAssignment,
        )
        from core.orders import Order, OrderPlan, OrderStatus
        from core.scheduling.task_allocator import Task

        # Restore robot states
        for rid, fs_data in data.get("robot_states", {}).items():
            cap_data = fs_data.get("capability", {})
            env_data = cap_data.get("env", {})
            cap = CapabilityVector(
                payload_kg=cap_data.get("payload_kg", 0.0),
                max_speed=cap_data.get("max_speed", 1.5),
                supported_models=cap_data.get("supported_models", []),
                action_primitives={
                    ActionPrimitive(a)
                    for a in cap_data.get("action_primitives", [0])
                },
                env=EnvConstraints(
                    max_grade=env_data.get("max_grade", 0.0),
                    floor_threshold=env_data.get("floor_threshold", 0.0),
                    min_friction=env_data.get("min_friction", 0.0),
                ),
                supports_reverse=cap_data.get("supports_reverse", False),
            )
            sh_data = fs_data.get("sensor_health", {})
            pose_data = fs_data.get("pose", {})
            fs = FleetState(
                robot_id=fs_data["robot_id"],
                boot_id=fs_data.get("boot_id", ""),
                pose=Pose(
                    x=pose_data.get("x", 0.0),
                    y=pose_data.get("y", 0.0),
                    theta=pose_data.get("theta", 0.0),
                    last_node_id=pose_data.get("last_node_id", ""),
                    position_initialized=pose_data.get("position_initialized", True),
                ),
                battery_percent=fs_data.get("battery_percent", 0.0),
                mode=RobotMode(fs_data.get("mode", 0)),
                errors=fs_data.get("errors", []),
                sensor_health=SensorHealth(
                    velocity_sensor=HealthStatus(sh_data.get("velocity_sensor", 0)),
                    lidar=HealthStatus(sh_data.get("lidar", 0)),
                    camera=HealthStatus(sh_data.get("camera", 0)),
                    time_sync=HealthStatus(sh_data.get("time_sync", 0)),
                ),
                velocity=fs_data.get("velocity", 0.0),
                last_seen_monotonic=fs_data.get("last_seen_monotonic", 0.0),
                capability=cap,
                degraded=fs_data.get("degraded", False),
                version=fs_data.get("version", "5.0"),
            )
            self._robot_states[rid] = fs

        # Re-link robot → adapter if brand mapping was saved
        for rid, brand in data.get("robot_brands", {}).items():
            adapter = self._adapters.get(brand)
            if adapter is not None and rid in self._robot_states:
                self._robot_adapter[rid] = adapter

        # Restore active assignments
        for rid, a_data in data.get("active_assignments", {}).items():
            self._active_assignments[rid] = TaskAssignment(
                task_id=a_data["task_id"],
                path=a_data.get("path", []),
                max_speed=a_data.get("max_speed", 1.5),
                version=a_data.get("version", "5.0"),
            )

        # Restore task queue
        self._task_queue.clear()
        for t_data in data.get("task_queue", []):
            self._task_queue.append(Task(
                task_id=t_data["task_id"],
                start_lane=t_data["start_lane"],
                end_lane=t_data["end_lane"],
                priority=t_data.get("priority", 0),
                created_at=t_data.get("created_at", 0.0),
                deadline=t_data.get("deadline", 0.0),
                action_primitives={
                    ActionPrimitive(a)
                    for a in t_data.get("action_primitives", [0])
                },
                required_payload_kg=t_data.get("required_payload_kg", 0.0),
            ))

        # Restore order plans
        self._order_plans.clear()
        for oid, p_data in data.get("order_plans", {}).items():
            o_data = p_data["order"]
            order = Order(
                order_id=o_data["order_id"],
                origin_lane=o_data["origin_lane"],
                destination_lane=o_data["destination_lane"],
                actions=[ActionPrimitive(a) for a in o_data.get("actions", [0])],
                payload_kg=o_data.get("payload_kg", 0.0),
                priority=o_data.get("priority", 0),
                status=OrderStatus[o_data.get("status", "PENDING")],
            )
            tasks = [
                Task(
                    task_id=t_data["task_id"],
                    start_lane=t_data["start_lane"],
                    end_lane=t_data["end_lane"],
                    priority=t_data.get("priority", 0),
                    created_at=t_data.get("created_at", 0.0),
                    deadline=t_data.get("deadline", 0.0),
                    action_primitives={
                        ActionPrimitive(a)
                        for a in t_data.get("action_primitives", [0])
                    },
                    required_payload_kg=t_data.get("required_payload_kg", 0.0),
                )
                for t_data in p_data["tasks"]
            ]
            self._order_plans[oid] = OrderPlan(order=order, tasks=tasks)

        # Restore simple maps
        self._task_order = dict(data.get("task_order", {}))
        self._order_completion = {
            oid: set(s) for oid, s in data.get("order_completion", {}).items()
        }
        self._task_retries = dict(data.get("task_retries", {}))
        self._robot_lane = dict(data.get("robot_lane", {}))

    # ── helpers ──────────────────────────────────────────────────
    def _worm_event(self, now: float, category: str, robot_id: str, payload: dict) -> None:
        self.worm.write(now, category, robot_id, payload)
        self.metrics.inc("worm_records")

    def register_charger(self, bay_id: str) -> None:
        self.charger.register_bay(bay_id)

    def register_lift(self, lift_id: str) -> None:
        self.lift.register(lift_id)

    def register_intersection(self, intersection_id: str) -> None:
        self.traffic.register(intersection_id)

    def add_lane(self, lane: Lane) -> None:
        self.fmap.add_lane(lane)
