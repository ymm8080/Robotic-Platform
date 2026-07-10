"""Tests for the v4.0 red-team adjustments: capability filtering, dynamic
obstacle cross-validation, deadlock break, 5s behavior timeout, open-loop
retreat, failover degrade semantics, unsafe speed cap."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.adapter.fleet_adapter import FleetAdapter
from core.adapter.shadow_state_machine import CircuitState
from core.messages import (
    ActionPrimitive,
    CapabilityVector,
    EnvConstraints,
    FleetState,
    Pose,
    RobotMode,
)
from core.platform.failover_degrade import FailoverDegrade
from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.platform.robot_as_obstacle import RobotAsObstacle
from core.safety.safe_distance import SafeDistanceCalculator
from core.scheduling.task_allocator import Task, TaskAllocator
from core.scheduling.traffic_light_controller import (
    LightPhase,
    TrafficLightController,
)
from core.governance.reputation_engine import ReputationEngine


def _robot(
    rid: str,
    *,
    cap: CapabilityVector | None = None,
    degraded: bool = False,
    mode: RobotMode = RobotMode.IDLE,
) -> FleetState:
    return FleetState(
        robot_id=rid,
        boot_id="b1",
        pose=Pose(x=0.0, y=0.0, last_node_id="A"),
        battery_percent=80.0,
        mode=mode,
        capability=cap or CapabilityVector(
            payload_kg=50.0,
            max_speed=1.5,
            action_primitives={ActionPrimitive.MOVE},
        ),
        degraded=degraded,
    )


# ── capability filtering (补丁3) ──────────────────────────────
def test_allocator_filters_by_action_primitive():
    rep = ReputationEngine()
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L_A", "A", "B", length=5.0))
    alloc = TaskAllocator(rep, lane_lookup=fmap.lane)
    # robot that can only MOVE vs task needing DOCK
    mover = _robot("R1")
    docker = _robot(
        "R2",
        cap=CapabilityVector(
            payload_kg=50.0,
            action_primitives={ActionPrimitive.MOVE, ActionPrimitive.DOCK},
        ),
    )
    task = Task("T1", "A", "B", action_primitives={ActionPrimitive.MOVE, ActionPrimitive.DOCK})
    res = alloc.allocate(task, [mover, docker])
    assert res.assigned and res.robot_id == "R2"


def test_allocator_filters_by_env_constraint():
    rep = ReputationEngine()
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L_A", "A", "B", length=5.0, env=EnvConstraints(max_grade=0.2, floor_threshold=0.05)))
    alloc = TaskAllocator(rep, lane_lookup=fmap.lane)
    flat_bot = _robot("R1", cap=CapabilityVector(payload_kg=50.0, action_primitives={ActionPrimitive.MOVE}, env=EnvConstraints()))
    climber = _robot(
        "R2",
        cap=CapabilityVector(
            payload_kg=50.0,
            action_primitives={ActionPrimitive.MOVE},
            env=EnvConstraints(max_grade=0.3, floor_threshold=0.1),
        ),
    )
    task = Task("T1", "L_A", "B")
    res = alloc.allocate(task, [flat_bot, climber])
    assert res.assigned and res.robot_id == "R2"  # flat_bot can't traverse grade


def test_allocator_rejects_degraded_robot():
    rep = ReputationEngine()
    alloc = TaskAllocator(rep)
    degraded = _robot("R1", degraded=True)
    healthy = _robot("R2")
    res = alloc.allocate(Task("T1", "A", "B"), [degraded, healthy])
    assert res.assigned and res.robot_id == "R2"


def test_allocator_no_capable_robot_reason():
    rep = ReputationEngine()
    alloc = TaskAllocator(rep)
    weak = _robot("R1", cap=CapabilityVector(payload_kg=5.0))
    res = alloc.allocate(Task("T1", "A", "B", required_payload_kg=50.0), [weak])
    assert not res.assigned
    assert res.reason == "no_capable_robot"


# ── dynamic obstacle cross-validation (v4.0 §5.3) ─────────────
def test_obstacle_cross_validation_requires_two_brands():
    fmap = FixedLaneMap()
    # single-brand observation → not confirmed (outlier rejection)
    fmap.report_observation(1.0, 1.0, robot_id="R1", brand="MIR", now=0.0)
    assert fmap.confirmed_obstacles() == []
    # second brand observes same spot → confirmed
    fmap.report_observation(1.0, 1.0, robot_id="R2", brand="OTTO", now=1.0)
    assert len(fmap.confirmed_obstacles()) == 1


def test_obstacle_confidence_decay_erases():
    fmap = FixedLaneMap()
    fmap.report_observation(2.0, 2.0, robot_id="R1", brand="MIR", now=0.0)
    fmap.report_observation(2.0, 2.0, robot_id="R2", brand="OTTO", now=0.0)
    assert len(fmap.confirmed_obstacles()) == 1
    # decay: 5s × 0.7 each tick; after enough ticks < 0.3 → erased
    now = 0.0
    for _ in range(5):
        now += FixedLaneMap.DECAY_INTERVAL
        fmap.decay_obstacles(now)
    assert fmap.confirmed_obstacles() == []


# ── robot-as-obstacle rectangle ───────────────────────────────
def test_robot_footprint_rectangle_collision():
    fmap = FixedLaneMap()
    rob = RobotAsObstacle(fmap)
    rob.update("R1", x=0.0, y=0.0, theta=0.0, velocity=0.0, rtt=0.0, half_length=0.4, half_width=0.3)
    # inside the body
    assert rob.collides(0.2, 0.1) == "R1"
    # outside body + corridor
    assert rob.collides(5.0, 5.0) is None


# ── traffic light deadlock break ──────────────────────────────
def test_deadlock_break_forces_low_priority_retreat():
    tlc = TrafficLightController()
    tlc.register("X1")
    # both directions waiting since t=0
    tlc.report_waiting_robot("X1", "RA", direction=0, priority=5, now=0.0)
    tlc.report_waiting_robot("X1", "RB", direction=1, priority=1, now=0.0)
    breaks = tlc.detect_deadlocks(now=20.0, threshold=15.0)
    assert len(breaks) == 1
    # low priority (1 < 5) retreats
    assert breaks[0].retreat_robot_id == "RB"
    assert breaks[0].metres == 5.0


def test_yellow_blocks_new_entries():
    tlc = TrafficLightController()
    it = tlc.register("X1")
    it.phase = LightPhase.GREEN
    it.current_direction = 0
    assert tlc.may_enter("X1", 0) is True
    it.phase = LightPhase.YELLOW
    assert tlc.may_enter("X1", 0) is False  # new vehicles prohibited
    assert tlc.may_enter("X1", 1) is False


# ── adapter 5s behavior timeout + open-loop retreat ──────────
def test_behavior_timeout_5s_trips_breaker():
    fa = FleetAdapter()
    fa.expect_behavior("R1", RobotMode.TASKING, now=0.0)
    # before deadline → no trip
    fa.tick(now=1.0)
    assert fa.shadow.breaker_state("R1") is CircuitState.CLOSED
    # past 5s deadline, behavior not observed → trip + retreat
    events = fa.tick(now=6.0)
    assert fa.shadow.breaker_state("R1") is CircuitState.OPEN
    assert any("BEHAVIOR_TIMEOUT_5S" in e for e in events)
    assert any(c.action == "RETREAT" and c.cmd_vel.linear_x < 0 for c in fa.pending_commands)


def test_open_loop_retreat_cmd_vel():
    fa = FleetAdapter()
    fa.scs_timeout("R1", now=0.0)  # 1st failure
    fa.scs_timeout("R1", now=1.0)  # 2nd
    fa.scs_timeout("R1", now=2.0)  # 3rd → OPEN
    cmd = [c for c in fa.pending_commands if c.action == "RETREAT"]
    assert cmd and cmd[0].cmd_vel.angular_z == 0.0
    assert cmd[0].metres == 5.0


def test_no_reverse_support_downgrades_to_hold():
    fa = FleetAdapter()
    bot = _robot("R1", cap=CapabilityVector(payload_kg=50.0, supports_reverse=False))
    fa.ingest_state(bot, now=0.0)
    fa.scs_timeout("R1", now=0.0)
    fa.scs_timeout("R1", now=1.0)
    fa.scs_timeout("R1", now=2.0)
    holds = [c for c in fa.pending_commands if c.action == "HOLD"]
    assert holds and holds[0].reason == "no_reverse_support"


def test_waypoint_immutability_refuses_skip():
    fa = FleetAdapter()
    from core.messages import TaskAssignment

    fa.dispatch("R1", TaskAssignment(task_id="T1", path=["A", "B", "C"], max_speed=1.0), now=0.0)
    # must acknowledge A first; skipping to B refused
    assert fa.advance_waypoint("R1", "B") is False
    assert fa.advance_waypoint("R1", "A") is True
    assert fa.advance_waypoint("R1", "B") is True


def test_speed_limit_enforced():
    fa = FleetAdapter()
    assert fa.enforce_speed_limit("R1", commanded=2.0, max_speed=1.0) == 1.0
    assert fa.enforce_speed_limit("R1", commanded=0.5, max_speed=1.0) == 0.5


# ── failover degrade semantics (补丁5) ────────────────────────
def test_degraded_mode_only_last_goal_and_rejects_new_tasks():
    fd = FailoverDegrade()
    fd.observe(_robot("R1"), now=0.0)
    fd.tick(now=4.0)  # >3s → DEGRADED
    assert fd.accepts_new_tasks("R1", now=4.0) is False
    rs = fd._robots["R1"]
    assert rs.only_last_goal is True
    assert rs.local_cache_valid is True
    # manual recovery restores
    fd.manual_recover("R1")
    assert fd.accepts_new_tasks("R1", now=4.0) is True


def test_split_brain_detection():
    fd = FailoverDegrade()
    assert fd.reconcile_state_revision(10) is True
    assert fd.reconcile_state_revision(5) is False  # stale peer → split brain
    assert fd.split_brain is True


# ── unsafe distance speed cap (0.2 m/s) ───────────────────────
def test_unsafe_gap_caps_to_0_2():
    calc = SafeDistanceCalculator()
    # at 1.0 m/s, D_safe ≈ 1.9 m; gap of 1.0 m is unsafe → cap 0.2
    capped = calc.speed_cap_for_gap(velocity=1.0, rtt=0.1, available_gap=1.0)
    assert capped == 0.2
    # gap sufficient → no cap
    assert calc.speed_cap_for_gap(velocity=1.0, rtt=0.1, available_gap=5.0) == 1.0
