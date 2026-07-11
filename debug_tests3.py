"""Debug: trace R-003 commands in detail."""
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

for i in range(240):
    result = harness.tick(1)
    r3 = harness.fleet.get_robot("R-003")
    if r3 and (r3.held or i % 10 == 9):
        cmds = [(c.robot_id, c.action, getattr(c, 'reason', '')) for c in result.commands if c.robot_id == "R-003"]
        holds = [e for e in result.events if "R-003" in e]
        print(f"t{i+1} now={harness.now:.1f} traffic={it.phase}/d{it.current_direction} | R3: lane={r3.current_lane_id} dist={r3.distance_along_lane:.2f} held={r3.held} cmds={cmds} events={holds}")
