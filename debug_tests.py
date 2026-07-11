"""Debug script for failing tests."""
import sys
sys.path.insert(0, ".")

from traffic_coordinator_v5.tests.test_simulator_scenarios import (
    CoordinatorHarness, demo_map
)
from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.scheduling.traffic_light_controller import LightPhase
from traffic_coordinator_v5.simulator.robot import SimRobotMode

# ── Test intersection_conflict ──
print("=== test_intersection_conflict ===")
fmap = FixedLaneMap()
fmap.add_lane(Lane("L_A_B", "A", "B", length=2.0, max_speed=1.5, intersection_id="X1", direction=0))
fmap.add_lane(Lane("L_X_B", "X", "B", length=20.0, max_speed=1.5, intersection_id="X1", direction=0))
fmap.add_lane(Lane("L_Y_B", "Y", "B", length=30.0, max_speed=1.5, intersection_id="X1", direction=1))
fmap.add_lane(Lane("L_B_Z1", "B", "Z1", length=20.0, max_speed=1.5))
fmap.add_lane(Lane("L_B_Z2", "B", "Z2", length=20.0, max_speed=1.5))
fmap.add_lane(Lane("L_B_Z3", "B", "Z3", length=20.0, max_speed=1.5))

positions = {
    "A": (0.0, 0.0), "X": (0.0, 30.0), "Y": (55.0, 30.0),
    "B": (10.0, 0.0), "Z1": (30.0, 0.0), "Z2": (30.0, 10.0), "Z3": (30.0, -10.0),
}
harness = CoordinatorHarness(fmap, lane_positions=positions)
harness.coordinator.register_intersection("X1")
it = harness.coordinator.traffic.get("X1")
it.phase = LightPhase.GREEN
it.current_direction = 0
it.phase_started_at = 0.0

harness.add_robot("R-001", "L_A_B")
harness.add_robot("R-002", "L_X_B")
harness.add_robot("R-003", "L_Y_B")
harness.submit_order("o1", "L_A_B", "L_B_Z1")
harness.submit_order("o2", "L_X_B", "L_B_Z2")
harness.submit_order("o3", "L_Y_B", "L_B_Z3")

intersection_holds = 0
collision_holds = 0
for i in range(20):
    result = harness.tick(1)
    if result is not None:
        ih = sum(1 for e in result.events if e.startswith("INTERSECTION_HOLD"))
        ch = sum(1 for e in result.events if e.startswith("COLLISION_HOLD"))
        intersection_holds += ih
        collision_holds += ch
        if ih or ch or i < 5:
            print(f"  tick {i+1}: IH={ih}, CH={ch}, events={result.events[:5]}")
            for rid, robot in harness.fleet._robots.items():
                print(f"    {rid}: mode={robot.mode}, held={robot.held}, lane={robot.current_lane_id}, dist={robot.distance_along_lane:.2f}")
            print(f"    traffic: phase={it.phase}, dir={it.current_direction}, waiting={it.vehicle_waiting}")

print(f"Total after 20 ticks: IH={intersection_holds}, CH={collision_holds}")
print(f"Robot modes: {[r.mode for r in harness.fleet._robots.values()]}")
print(f"Active assignments: {list(harness.coordinator._active_assignments.keys())}")

# ── Test safe_distance ──
print("\n=== test_safe_distance ===")
fmap2 = FixedLaneMap()
fmap2.add_lane(Lane("L_A_B", "A", "B", length=50.0, max_speed=2.0))
fmap2.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=2.0))

harness2 = CoordinatorHarness(fmap2)
r1 = harness2.add_robot("R-001", "L_A_B", max_speed=1.0)
r2 = harness2.add_robot("R-002", "L_A_B", max_speed=0.5)

path_order = {
    "orderId": "o1",
    "nodes": [
        {"nodeId": "L_A_B", "sequenceId": 0, "released": True},
        {"nodeId": "L_B_C", "sequenceId": 1, "released": True},
    ],
}
r1.assign_order(path_order)
r2.assign_order(path_order)
r2.distance_along_lane = 5.0

speed_cap_seen = False
collision_holds2 = 0
for i in range(20):
    result = harness2.tick(1)
    if result is not None:
        if any(cmd.action == "SPEED_CAP" for cmd in result.commands):
            speed_cap_seen = True
        ch = sum(1 for e in result.events if e.startswith("COLLISION_HOLD"))
        collision_holds2 += ch
        if ch or i < 5:
            print(f"  tick {i+1}: CH={ch}, events={result.events[:5]}")
            for rid, robot in harness2.fleet._robots.items():
                print(f"    {rid}: lane={robot.current_lane_id}, dist={robot.distance_along_lane:.2f}, vel={robot.velocity:.2f}")

print(f"Total after 20 ticks: speed_cap={speed_cap_seen}, CH={collision_holds2}")

# ── Test deadlock_break ──
print("\n=== test_deadlock_break ===")
fmap3 = FixedLaneMap()
fmap3.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5, intersection_id="X1", direction=0))
fmap3.add_lane(Lane("L_B_A", "B", "A", length=10.0, max_speed=1.5, intersection_id="X1", direction=1))

harness3 = CoordinatorHarness(fmap3)
harness3.coordinator.register_intersection("X1")
r1 = harness3.add_robot("R-001", "L_A_B")
r2 = harness3.add_robot("R-002", "L_B_A")

harness3.submit_order("o1", "L_A_B", "L_A_B")
harness3.submit_order("o2", "L_B_A", "L_B_A")

harness3.tick(1)
r1.distance_along_lane = 4.9
r2.distance_along_lane = 4.9

deadlock_breaks = 0
for i in range(80):
    result = harness3.tick(1)
    if result is not None:
        deadlock_breaks += len(result.deadlocks)
        if result.deadlocks or i < 5:
            print(f"  tick {i+1}: deadlocks={result.deadlocks}")
            for rid, robot in harness3.fleet._robots.items():
                print(f"    {rid}: lane={robot.current_lane_id}, dist={robot.distance_along_lane:.2f}")

print(f"Total after 80 ticks: deadlock_breaks={deadlock_breaks}")
