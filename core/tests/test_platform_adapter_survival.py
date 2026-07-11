"""Tests for platform service layer, adapter, governance, survival."""
from __future__ import annotations

import tempfile
from pathlib import Path

from core.adapter.fleet_adapter import FleetAdapter
from core.adapter.shadow_state_machine import CircuitState, ShadowStateMachine
from core.config import ChargerConfig, LivenessConfig
from core.governance.economic_model import EconomicModel, RobotCostProfile
from core.governance.reputation_engine import ReputationEngine
from core.messages import FleetState, Pose, RobotMode
from core.platform.charger_reservation import ChargerReservation, ChargerState
from core.platform.failover_degrade import FailoverDegrade
from core.platform.fixed_lane_map import FixedLaneMap, Lane, SpeedClass
from core.platform.lift_manager import LiftManager, LiftState
from core.platform.robot_as_obstacle import RobotAsObstacle
from core.survival.version_router import VersionedMessage, VersionRouter
from core.survival.worm_blackbox import WormBlackbox


# ── fixed lane map ─────────────────────────────────────────────
def test_lane_map_layers():
    m = FixedLaneMap()
    m.add_lane(Lane("L1", "A", "B", length=5.0, speed_class=SpeedClass.FAST))
    m.add_lane(Lane("L2", "B", "C", length=3.0, speed_class=SpeedClass.SLOW))
    assert m.is_traversable("L1")
    m.block_lane("L1")
    assert not m.is_traversable("L1")  # semantic overlay, physical intact
    assert m.lane("L1") is not None
    assert m.ground_truth_checksum()  # change detection works


# ── robot as obstacle ──────────────────────────────────────────
def test_robot_as_obstacle_bubble_and_collision():
    m = FixedLaneMap()
    rob = RobotAsObstacle(m)
    rob.update("R1", x=0.0, y=0.0, theta=0.0, velocity=1.0, rtt=0.1)
    # a point inside R1's footprint + corridor collides
    assert rob.collides(0.5, 0.0) == "R1"
    # far away → no collision
    assert rob.collides(10.0, 10.0) is None


def test_robot_as_obstacle_manual_wall():
    m = FixedLaneMap()
    rob = RobotAsObstacle(m)
    rob.mark_manual("R1", x=2.0, y=2.0)
    assert rob.footprints()[0].corridor == 1.5
    assert m.overlay.virtual_walls  # wall injected into semantic layer


# ── failover / degrade ────────────────────────────────────────
def test_failover_degrade_transitions():
    cfg = LivenessConfig(offline_to_degraded=3.0, offline_to_offline=60.0, degraded_max_speed=0.3)
    fd = FailoverDegrade(cfg)
    st = FleetState(robot_id="R1", boot_id="b1", pose=Pose(x=0.0, y=0.0), battery_percent=80.0)
    fd.observe(st, now=0.0)
    # no transition yet
    assert fd.tick(now=1.0) == []
    # >3s → DEGRADED
    trans = fd.tick(now=4.0)
    assert any("DEGRADED" in t[1] for t in trans)
    assert fd.degraded_speed_cap("R1") == 0.3
    # >60s → OFFLINE
    trans = fd.tick(now=61.0)
    assert any("OFFLINE" in t[1] for t in trans)
    assert "R1" in fd.offline_robots()


def test_failover_detects_boot_drift():
    fd = FailoverDegrade()
    fd.observe(FleetState(robot_id="R1", boot_id="b1", pose=Pose(x=0.0, y=0.0), battery_percent=80.0), now=0.0)
    events = fd.observe(
        FleetState(robot_id="R1", boot_id="b2", pose=Pose(x=0.0, y=0.0), battery_percent=80.0), now=1.0
    )
    assert any("BOOT_ID_CHANGED" in e for e in events)


# ── charger reservation ───────────────────────────────────────
def test_charger_force_lock_below_threshold():
    cr = ChargerReservation(ChargerConfig(force_lock_threshold=20.0))
    cr.register_bay("CH1")
    assert cr.needs_force_lock(15.0)
    bay = cr.reserve("R1", battery_percent=15.0, now=0.0)
    assert bay == "CH1"
    assert cr._bays["CH1"].state is ChargerState.RESERVED
    cr.occupy("R1")
    assert cr._bays["CH1"].state is ChargerState.OCCUPIED
    cr.release("R1")
    assert cr._bays["CH1"].state is ChargerState.FREE


def test_charger_no_lock_above_threshold():
    cr = ChargerReservation()
    cr.register_bay("CH1")
    assert cr.reserve("R1", battery_percent=80.0, now=0.0) is None


# ── lift manager ──────────────────────────────────────────────
def test_lift_single_occupancy_and_release():
    lm = LiftManager()
    lm.register("L1")
    assert lm.request("L1", "R1", target_floor=2, now=0.0)
    # second robot cannot grab an occupied lift
    assert not lm.request("L1", "R2", target_floor=3, now=1.0)
    lm.tick(now=1.0)  # MOVING → OCCUPIED
    assert lm._lifts["L1"].state is LiftState.OCCUPIED
    assert lm.release("L1", "R1")
    assert lm._lifts["L1"].state is LiftState.IDLE


# ── shadow state machine + fleet adapter ──────────────────────
def test_shadow_mismatch_detected():
    sm = ShadowStateMachine()
    sm.expect("R1", RobotMode.TASKING)
    st = FleetState(robot_id="R1", boot_id="b1", pose=Pose(x=0.0, y=0.0), battery_percent=80.0, mode=RobotMode.IDLE)
    mm = sm.reconcile(st, now=0.0)
    assert mm is not None
    assert mm.expected == "TASKING"


def test_circuit_breaker_trips_and_fallback():
    fa = FleetAdapter()
    now = 0.0
    tripped = False
    for _ in range(3):
        tripped = fa.scs_timeout("R1", now) or tripped
        now += 1.0
    assert fa.shadow.breaker_state("R1") is CircuitState.OPEN
    assert fa.shadow.should_fallback("R1")
    assert any(c.action == "RETREAT" for c in fa.pending_commands)


# ── reputation + economic ──────────────────────────────────────
def test_reputation_violation_lowers_score():
    rep = ReputationEngine()
    base = rep.score("R1")
    rep.record_good("R1", 0.0)
    rep.record_good("R1", 1.0)
    good = rep.score("R1")
    rep.record_violation("R1", 2.0)
    assert rep.score("R1") < good
    assert base == 0.5  # zero-trust default for unknown


def test_economic_model_disabled_by_default():
    rep = ReputationEngine()
    em = EconomicModel(rep)
    em.register(RobotCostProfile(robot_id="R1", base_cost_per_km=10.0))
    assert not em.enabled()
    assert em.marginal_cost_per_km("R1") == 0.0  # γ=0


# ── WORM blackbox ─────────────────────────────────────────────
def test_worm_chain_and_replay():
    with tempfile.TemporaryDirectory() as d:
        wb = WormBlackbox(sink_path=Path(d) / "worm.jsonl")
        wb.write(0.0, "EVENT", "R1", {"v": 1})
        wb.write(1.0, "ERROR", "R1", {"code": "ERR_SCS_TIMEOUT"})
        wb.write(2.0, "ESTOP", "R2", {"zone": "Z1"})
        assert wb.verify_chain()
        recs = wb.replay(robot_id="R1")
        assert len(recs) == 2
        assert all(r.robot_id == "R1" for r in recs)
        # tamper detection
        wb._records[1].payload = {"code": "TAMPERED"}
        assert not wb.verify_chain()


def test_worm_disk_warning():
    wb = WormBlackbox(disk_free_pct=15.0)
    assert wb.disk_warning()
    wb2 = WormBlackbox(disk_free_pct=50.0)
    assert not wb2.disk_warning()


def test_worm_restart_preserves_chain():
    """Restart must restore prev_hash so new records link to prior history."""
    with tempfile.TemporaryDirectory() as d:
        sink = Path(d) / "worm.jsonl"
        wb1 = WormBlackbox(sink_path=sink)
        wb1.write(100.0, "EVENT", "R1", {"v": 1})
        wb1.write(101.0, "ERROR", "R1", {"code": "ERR_TIMEOUT"})
        assert wb1.verify_chain()

        # Simulate restart — new instance reads same sink file
        wb2 = WormBlackbox(sink_path=sink)
        assert len(wb2.records()) == 2
        assert wb2.verify_chain()
        # New record must chain to the last record from wb1
        rec = wb2.write(102.0, "EVENT", "R2", {"action": "recover"})
        assert rec.prev_hash == wb1.records()[-1].hash
        assert wb2.verify_chain()


# ── version router ────────────────────────────────────────────
def test_version_router_upgrades_v4_fields():
    vr = VersionRouter()
    msg = VersionedMessage(version="4.1", body={"robotId": "R1", "batteryLevel": 80})
    out = vr.normalise(msg)
    assert out.version == "5.0"
    assert "robot_id" in out.body and "robotId" not in out.body
    assert out.body["battery_percent"] == 80


def test_version_router_rejects_unsupported():
    vr = VersionRouter()
    try:
        vr.normalise(VersionedMessage(version="2.0", body={}))
        assert False, "should have raised"
    except ValueError:
        pass


# ── cold-start stagger (陷阱 #3) ─────────────────────────────────
def test_cold_start_stagger_registration():
    """3 robots ingested within 1s → only 1 registered immediately, 2 queued."""
    from core.config import CoreConfig
    from core.coordinator import RobotPlatformCoordinator
    from core.adapter.fleet_adapter import FleetAdapter

    cfg = CoreConfig(registration_stagger_seconds=5.0)
    tc = RobotPlatformCoordinator(config=cfg)
    adapter = FleetAdapter("test_brand")
    tc.register_adapter(adapter)

    now = 0.0
    tc.ingest_uplink(
        "test_brand",
        {"robotId": "R1", "batteryLevel": 90, "agvPosition": {"x": 0, "y": 0, "theta": 0}},
        now,
    )
    tc.ingest_uplink(
        "test_brand",
        {"robotId": "R2", "batteryLevel": 85, "agvPosition": {"x": 1, "y": 0, "theta": 0}},
        now + 0.1,
    )
    tc.ingest_uplink(
        "test_brand",
        {"robotId": "R3", "batteryLevel": 80, "agvPosition": {"x": 2, "y": 0, "theta": 0}},
        now + 0.2,
    )

    # R1 registered immediately (first robot, no stagger gate)
    assert "R1" in tc._robot_states
    # R2, R3 queued (within 5s stagger window)
    assert "R2" not in tc._robot_states
    assert "R3" not in tc._robot_states
    assert len(tc._pending_registrations) == 2

    # Tick at t=5: R2 dequeued
    tc.tick(5.0)
    assert "R2" in tc._robot_states
    assert len(tc._pending_registrations) == 1

    # Tick at t=10: R3 dequeued
    tc.tick(10.0)
    assert "R3" in tc._robot_states
    assert len(tc._pending_registrations) == 0


def test_cold_start_stagger_disabled_when_zero():
    """When stagger is 0, all robots register immediately (backward compat)."""
    from core.config import CoreConfig
    from core.coordinator import RobotPlatformCoordinator
    from core.adapter.fleet_adapter import FleetAdapter

    cfg = CoreConfig(registration_stagger_seconds=0.0)
    tc = RobotPlatformCoordinator(config=cfg)
    adapter = FleetAdapter("test_brand")
    tc.register_adapter(adapter)

    tc.ingest_uplink(
        "test_brand",
        {"robotId": "R1", "batteryLevel": 90, "agvPosition": {"x": 0, "y": 0, "theta": 0}},
        0.0,
    )
    tc.ingest_uplink(
        "test_brand",
        {"robotId": "R2", "batteryLevel": 85, "agvPosition": {"x": 1, "y": 0, "theta": 0}},
        0.1,
    )
    assert "R1" in tc._robot_states
    assert "R2" in tc._robot_states
    assert len(tc._pending_registrations) == 0
