"""Tests for ConflictLayerCoordinator — 三层次冲突空间 (v7 Phase 4 task 1)."""
from __future__ import annotations

from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.scheduling.conflict_coordinator import ConflictLayerCoordinator
from core.scheduling.mapf_engine import AgentRequest, MAPFEngine
from core.scheduling.traffic_light_controller import LightPhase, TrafficLightController


def _two_corridor_map() -> FixedLaneMap:
    """A-B-C corridor + D-E-F corridor (disjoint) + intersection IX at C→G."""
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L1", "A", "B", length=3.0))
    fmap.add_lane(Lane("L2", "B", "C", length=3.0))
    fmap.add_lane(Lane("L3", "D", "E", length=3.0))
    fmap.add_lane(Lane("L4", "E", "F", length=3.0))
    fmap.add_lane(Lane("LX", "C", "G", length=2.0, intersection_id="IX", direction=0))
    return fmap


def _coord(
    fmap: FixedLaneMap, tlc: TrafficLightController | None = None
) -> ConflictLayerCoordinator:
    return ConflictLayerCoordinator(
        fmap, MAPFEngine(fmap, time_horizon=20), tlc or TrafficLightController()
    )


# ── L1 宏观分组 ──────────────────────────────────────────────
def test_interacting_agents_grouped_into_one_ecbs_run():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    res = coord.coordinate([AgentRequest("R1", "A", "C"), AgentRequest("R2", "A", "C")])
    assert len(res.groups) == 1
    assert set(res.groups[0]) == {"R1", "R2"}
    assert res.ecbs_group_count == 1


def test_disjoint_corridors_split_into_singleton_groups():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    res = coord.coordinate([AgentRequest("R1", "A", "C"), AgentRequest("R2", "D", "F")])
    assert res.ecbs_group_count == 0  # no shared nodes → no ECBS needed
    assert len(res.groups) == 2
    assert all(len(g) == 1 for g in res.groups)


def test_empty_requests_returns_empty():
    fmap = _two_corridor_map()
    coord = ConflictLayerCoordinator(fmap, MAPFEngine(fmap), TrafficLightController())
    res = coord.coordinate([])
    assert res.plans == {}
    assert res.groups == []


def test_single_agent_one_singleton_group():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    res = coord.coordinate([AgentRequest("R1", "A", "C")])
    assert res.ecbs_group_count == 0
    assert res.get("R1") is not None


# ── L2 区块内 ECBS ───────────────────────────────────────────
def test_all_agents_get_plans():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    res = coord.coordinate(
        [AgentRequest("R1", "A", "C"), AgentRequest("R2", "D", "F"), AgentRequest("R3", "A", "C")]
    )
    for aid in ("R1", "R2", "R3"):
        assert res.get(aid) is not None


# ── L3 路口门控 ──────────────────────────────────────────────
def test_intersection_red_blocks_crossing_move():
    fmap = _two_corridor_map()
    tlc = TrafficLightController()
    tlc.register("IX")  # default RED
    coord = _coord(fmap, tlc)
    res = coord.coordinate([AgentRequest("R1", "A", "G")])  # crosses IX
    blocked = res.blocked_gates()
    assert len(blocked) >= 1
    assert all(g.intersection_id == "IX" for g in blocked)
    assert all(not g.allowed for g in blocked)


def test_intersection_green_allows_crossing_move():
    fmap = _two_corridor_map()
    tlc = TrafficLightController()
    it = tlc.register("IX")
    it.phase = LightPhase.GREEN
    it.current_direction = 0  # matches Lane LX direction
    coord = _coord(fmap, tlc)
    res = coord.coordinate([AgentRequest("R1", "A", "G")])
    gates = [g for g in res.gates if g.intersection_id == "IX"]
    assert gates, "R1 crosses IX → gate must exist"
    assert all(g.allowed for g in gates)
    assert res.blocked_gates() == []


def test_non_intersection_moves_not_gated():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    # A→C never touches intersection lane LX
    res = coord.coordinate([AgentRequest("R1", "A", "C")])
    assert res.gates == []


# ── 三层联合 (DoD) ───────────────────────────────────────────
def test_three_layers_combined():
    fmap = _two_corridor_map()
    tlc = TrafficLightController()
    tlc.register("IX")
    coord = _coord(fmap, tlc)
    res = coord.coordinate(
        [
            AgentRequest("R1", "A", "C"),
            AgentRequest("R2", "A", "C"),  # shares corridor with R1 → ECBS group
            AgentRequest("R3", "D", "F"),  # disjoint → singleton
            AgentRequest("R4", "A", "G"),  # crosses IX → gated
        ]
    )
    # L1
    assert res.ecbs_group_count == 1
    # L2
    assert all(res.get(a) is not None for a in ("R1", "R2", "R3", "R4"))
    # L3
    assert res.blocked_gates(), "R4 must be gated at RED intersection"
