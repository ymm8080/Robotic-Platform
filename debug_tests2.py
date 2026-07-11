"""Debug: run full intersection test and check completion."""
import sys
sys.path.insert(0, ".")

from traffic_coordinator_v5.tests.test_simulator_scenarios import CoordinatorHarness
from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.scheduling.traffic_light_controller import LightPhase
from traffic_coordinator_v5.simulator.robot import SimRobotMode

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

collision_holds = 0
intersection_holds = 0
for i in range(240):
    result = harness.tick(1)
    if result is not None:
        collision_holds += sum(1 for e in result.events if e.startswith("COLLISION_HOLD"))
        intersection_holds += sum(1 for e in result.events if e.startswith("INTERSECTION_HOLD"))
    if i % 20 == 19 or i < 5:
        print(f"tick {i+1}: now={harness.now:.1f}, traffic={it.phase}/dir{it.current_direction}")
        for rid, robot in harness.fleet._robots.items():
            print(f"  {rid}: mode={robot.mode}, held={robot.held}, lane={robot.current_lane_id}, dist={robot.distance_along_lane:.2f}")

print(f"\nFinal: IH={intersection_holds}, CH={collision_holds}")
print(f"Robot modes: {[r.mode for r in harness.fleet._robots.values()]}")
print(f"Active assignments: {list(harness.coordinator._active_assignments.keys())}")
print(f"Task queue: {[t.task_id for t in harness.coordinator._task_queue]}")
