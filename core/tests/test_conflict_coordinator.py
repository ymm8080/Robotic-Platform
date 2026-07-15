"""Tests for ConflictLayerCoordinator."""

from __future__ import annotations

from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.scheduling.conflict_coordinator import ConflictLayerCoordinator
from core.scheduling.mapf_engine import AgentRequest, MAPFEngine
from core.scheduling.traffic_light_controller import LightPhase, TrafficLightController


def _two_corridor_map() -> FixedLaneMap:
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L1", "A", "B", length=3.0))
    fmap.add_lane(Lane("L2", "B", "C", length=3.0))
    fmap.add_lane(Lane("L3", "D", "E", length=3.0))
    fmap.add_lane(Lane("L4", "E", "F", length=3.0))
    fmap.add_lane(Lane("LX", "C", "G", length=2.0, intersection_id="IX", direction=0))
    return fmap


def _coord(fmap, tlc=None):
    return ConflictLayerCoordinator(
        fmap, MAPFEngine(fmap, time_horizon=20), tlc or TrafficLightController()
    )


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
    assert res.ecbs_group_count == 0
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


def test_groups_preserve_request_order():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    res = coord.coordinate(
        [
            AgentRequest("R3", "D", "F"),
            AgentRequest("R1", "A", "C"),
            AgentRequest("R2", "A", "C"),
        ]
    )
    assert res.groups[0] == ["R3"]
    assert res.groups[1] == ["R1", "R2"]
    assert res.request_order == ["R3", "R1", "R2"]


def test_all_agents_get_plans():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    res = coord.coordinate(
        [
            AgentRequest("R1", "A", "C"),
            AgentRequest("R2", "D", "F"),
            AgentRequest("R3", "A", "C"),
        ]
    )
    for aid in ("R1", "R2", "R3"):
        assert res.get(aid) is not None


def test_intersection_red_blocks_crossing_move():
    fmap = _two_corridor_map()
    tlc = TrafficLightController()
    tlc.register("IX")
    coord = _coord(fmap, tlc)
    res = coord.coordinate([AgentRequest("R1", "A", "G")])
    blocked = res.blocked_gates()
    assert len(blocked) >= 1
    assert all(g.intersection_id == "IX" for g in blocked)
    assert all(not g.allowed for g in blocked)


def test_intersection_green_allows_crossing_move():
    fmap = _two_corridor_map()
    tlc = TrafficLightController()
    it = tlc.register("IX")
    it.phase = LightPhase.GREEN
    it.current_direction = 0
    coord = _coord(fmap, tlc)
    res = coord.coordinate([AgentRequest("R1", "A", "G")])
    gates = [g for g in res.gates if g.intersection_id == "IX"]
    assert gates
    assert all(g.allowed for g in gates)
    assert res.blocked_gates() == []


def test_non_intersection_moves_not_gated():
    fmap = _two_corridor_map()
    coord = _coord(fmap)
    res = coord.coordinate([AgentRequest("R1", "A", "C")])
    assert res.gates == []


def test_model_filter_restricts_corridor():
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L1", "A", "B", length=3.0, allowed_models=["geek+"]))
    fmap.add_lane(Lane("L2", "B", "C", length=3.0, allowed_models=["geek+"]))
    fmap.add_lane(Lane("L3", "A", "D", length=5.0, allowed_models=["mir"]))
    fmap.add_lane(Lane("L4", "D", "C", length=5.0, allowed_models=["mir"]))
    coord = _coord(fmap)
    geek_nodes = coord._corridor_nodes(AgentRequest("R1", "A", "C", model="geek+"))
    mir_nodes = coord._corridor_nodes(AgentRequest("R2", "A", "C", model="mir"))
    assert "B" in geek_nodes
    assert "D" not in geek_nodes
    assert "D" in mir_nodes
    assert "B" not in mir_nodes


def test_no_model_filter_uses_all_lanes():
    fmap = FixedLaneMap()
    fmap.add_lane(Lane("L1", "A", "B", length=3.0, allowed_models=["geek+"]))
    fmap.add_lane(Lane("L2", "B", "C", length=3.0))
    coord = _coord(fmap)
    nodes = coord._corridor_nodes(AgentRequest("R1", "A", "C"))
    assert "B" in nodes


def test_three_layers_combined():
    fmap = _two_corridor_map()
    tlc = TrafficLightController()
    tlc.register("IX")
    coord = _coord(fmap, tlc)
    res = coord.coordinate(
        [
            AgentRequest("R1", "A", "C"),
            AgentRequest("R2", "A", "C"),
            AgentRequest("R3", "D", "F"),
            AgentRequest("R4", "A", "G"),
        ]
    )
    assert res.ecbs_group_count == 1
    assert all(res.get(a) is not None for a in ("R1", "R2", "R3", "R4"))
    assert res.blocked_gates()
