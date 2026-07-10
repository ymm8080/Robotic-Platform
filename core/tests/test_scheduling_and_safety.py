"""Tests for the v5.0 core scheduling + safety modules."""
from __future__ import annotations

import sys
from pathlib import Path

# make ``core`` importable when run from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.config import TrafficConfig
from core.messages import HealthStatus, Pose, RobotMode, SensorHealth
from core.safety.safe_distance import SafeDistanceCalculator
from core.scheduling.task_allocator import Task, TaskAllocator
from core.scheduling.traffic_light_controller import (
    LightPhase,
    TrafficLightController,
)
from core.scheduling.facility_manager import FacilityManager
from core.governance.reputation_engine import ReputationEngine


# ── safety distance ───────────────────────────────────────────
def test_safe_distance_dynamic_above_floor():
    calc = SafeDistanceCalculator()
    r = calc.compute(velocity=1.0, rtt=0.1)
    # S = 1.0*1.5 + 0.1*1.0 + 0.3 = 1.9
    assert abs(r.dynamic - 1.9) < 1e-6
    assert abs(r.applied - 1.9) < 1e-6
    assert not r.sensor_penalty


def test_safe_distance_never_below_hard_floor():
    calc = SafeDistanceCalculator()
    r = calc.compute(velocity=0.0, rtt=0.0)
    assert r.dynamic == 0.3
    assert r.applied == 1.5  # legal floor enforced
    assert r.floor == 1.5


def test_safe_distance_sensor_degrade_amplifies():
    calc = SafeDistanceCalculator()
    healthy = calc.compute(1.0, 0.1)
    degraded = calc.compute(1.0, 0.1, SensorHealth(lidar=HealthStatus.DEGRADED))
    assert degraded.sensor_penalty
    assert degraded.dynamic == healthy.dynamic * 1.5
    assert degraded.applied >= healthy.applied


# ── traffic light ─────────────────────────────────────────────
def test_traffic_light_green_to_yellow_on_timeout():
    cfg = TrafficConfig(max_green=10.0, yellow_duration=3.0, no_vehicle_wait=2.0)
    tlc = TrafficLightController(cfg)
    it = tlc.register("X1")
    it.phase = LightPhase.GREEN
    it.current_direction = 0
    it.phase_started_at = 0.0
    tlc.report_waiting("X1", 1, True)
    # before no_vehicle_wait → still green
    tlc.tick(1.0)
    assert it.phase is LightPhase.GREEN
    # after no_vehicle_wait → yellow
    tlc.tick(2.5)
    assert it.phase is LightPhase.YELLOW


def test_traffic_light_yellow_to_red_then_swap():
    cfg = TrafficConfig(yellow_duration=3.0, no_vehicle_wait=2.0, max_green=10.0)
    tlc = TrafficLightController(cfg)
    it = tlc.register("X2")
    it.phase = LightPhase.YELLOW
    it.phase_started_at = 0.0
    it.current_direction = 0
    tlc.tick(3.5)
    assert it.phase is LightPhase.RED
    # after red wait → swap direction + green
    it.phase_started_at = 3.5
    tlc.tick(6.0)
    assert it.phase is LightPhase.GREEN
    assert it.current_direction == 1


def test_traffic_light_emergency_forces_red():
    tlc = TrafficLightController()
    it = tlc.register("X3")
    it.phase = LightPhase.GREEN
    tlc.force_all_red("X3")
    tlc.tick(0.0)
    assert it.phase is LightPhase.RED
    assert it.emergency


# ── task allocator ─────────────────────────────────────────────
def _robot(rid: str, node: str = "A") -> object:
    from core.messages import ActionPrimitive, CapabilityVector, FleetState

    return FleetState(
        robot_id=rid,
        boot_id="b1",
        pose=Pose(x=0.0, y=0.0, last_node_id=node),
        battery_percent=80.0,
        mode=RobotMode.IDLE,
        capability=CapabilityVector(
            payload_kg=50.0, action_primitives={ActionPrimitive.MOVE}
        ),
    )


def test_allocator_picks_idle_with_best_utility():
    rep = ReputationEngine()
    rep.record_good("R1", 0.0)   # R1 has good reputation
    rep.record_violation("R2", 0.0)  # R2 penalised
    alloc = TaskAllocator(rep, distance_fn=lambda a, b: 1.0)
    task = Task(task_id="T1", start_lane="A", end_lane="B")
    res = alloc.allocate(task, [_robot("R1"), _robot("R2")])
    assert res.assigned
    assert res.robot_id == "R1"


def test_allocator_no_idle_returns_unassigned():
    rep = ReputationEngine()
    alloc = TaskAllocator(rep)
    busy = _robot("R1")
    busy.mode = RobotMode.TASKING
    res = alloc.allocate(Task("T1", "A", "B"), [busy])
    assert not res.assigned
    assert res.reason == "no_idle_robot"


# ── facility manager ──────────────────────────────────────────
def test_facility_lockdown_and_release():
    fm = FacilityManager()
    fm.register_zone("Z1")
    assert fm.lockdown("Z1", now=0.0)
    assert "Z1" in fm.locked_zones()
    fm.release("Z1")
    assert "Z1" not in fm.locked_zones()


def test_facility_reap_zombies():
    fm = FacilityManager()
    fm.occupy("Z1", "R1", now=0.0)
    reaped = fm.reap_zombies(now=35.0, hold_seconds=30.0)
    assert ("Z1", "R1") in reaped
