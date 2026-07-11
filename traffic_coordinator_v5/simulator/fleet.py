"""FleetSimulator — own the lane graph, robots, and MQTT client."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from traffic_coordinator_v5.simulator.map import LaneGraph
from traffic_coordinator_v5.simulator.mqtt_client import MqttVDAClient
from traffic_coordinator_v5.simulator.robot import RobotConfig, SimulatedRobot

logger = logging.getLogger(__name__)


class FleetSimulator:
    """Owns the lane graph, simulated robots, and optional MQTT client.

    ``tick_once(dt)`` advances every robot deterministically and is the
    primary hook for unit tests. The real-time loop is a thin wrapper around
    the same tick function.
    """

    def __init__(
        self,
        lane_graph: LaneGraph,
        brand: str = "generic",
        mqtt_client: MqttVDAClient | None = None,
        publish_interval: float = 0.5,
    ) -> None:
        self.lane_graph = lane_graph
        self._brand = brand
        self._robots: dict[str, SimulatedRobot] = {}
        self._mqtt = mqtt_client
        if self._mqtt is not None:
            self._mqtt.set_callbacks(
                on_order=self._route_order,
                on_instant_actions=self._route_instant_actions,
            )
        self._publish_interval = publish_interval
        self._last_publish: dict[str, float] = {}
        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def add_robot(
        self,
        robot_id: str,
        start_lane: str | None = None,
        battery: float = 80.0,
        config: RobotConfig | None = None,
    ) -> SimulatedRobot:
        """Create and register a new simulated robot."""
        robot = SimulatedRobot(
            robot_id=robot_id,
            brand=self._brand,
            lane_graph=self.lane_graph,
            current_lane_id=start_lane or self.lane_graph.first_lane() or "",
            battery_percent=battery,
            config=config or RobotConfig(),
        )
        self._robots[robot_id] = robot
        self._last_publish[robot_id] = 0.0
        if self._mqtt is not None:
            self._mqtt.add_robot(robot_id)
        return robot

    def get_robot(self, robot_id: str) -> SimulatedRobot | None:
        return self._robots.get(robot_id)

    def start(self) -> None:
        """Start the MQTT client and optional real-time tick thread."""
        if self._mqtt is not None:
            self._mqtt.connect()
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="fleet-sim-loop")
        self._thread.start()

    def stop(self) -> None:
        """Stop the tick thread and disconnect MQTT."""
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._mqtt is not None:
            self._mqtt.disconnect()

    def _run_loop(self) -> None:
        """Real-time loop: tick and publish at the configured interval.

        Tick and publish use independent schedules so that a slow tick_once
        does not delay state publishing (or vice versa).
        """
        last_tick = time.monotonic()
        next_tick = time.monotonic()
        next_publish = time.monotonic()
        while self._running and not self._stop_event.is_set():
            now = time.monotonic()
            if now >= next_tick:
                # Use actual elapsed time for physics accuracy; cap at 2x
                # interval to prevent physics explosions under heavy load.
                dt = min(now - last_tick, self._publish_interval * 2)
                last_tick = now
                self.tick_once(dt)
                next_tick = now + self._publish_interval
            if now >= next_publish:
                self._publish_states(now)
                next_publish = now + self._publish_interval
            sleep_dur = min(next_tick, next_publish) - time.monotonic()
            self._stop_event.wait(max(0.0, sleep_dur))

    def tick_once(self, dt: float) -> dict[str, list[str]]:
        """Advance every robot by ``dt`` seconds (deterministic).

        Returns a dict of ``{robot_id: [reached_lane_ids]}``.
        """
        reached: dict[str, list[str]] = {}
        for robot_id, robot in self._robots.items():
            reached[robot_id] = robot.tick(dt)
        return reached

    def publish_all_states(self) -> None:
        """Publish current state for every robot immediately."""
        if self._mqtt is None:
            return
        for robot_id, robot in self._robots.items():
            self._mqtt.publish_state(robot_id, robot.state_payload())

    def _publish_states(self, now: float) -> None:
        """Throttle state publishes to ``_publish_interval``."""
        if self._mqtt is None:
            return
        for robot_id, robot in self._robots.items():
            last = self._last_publish.get(robot_id, 0.0)
            if now - last >= self._publish_interval:
                self._mqtt.publish_state(robot_id, robot.state_payload())
                self._last_publish[robot_id] = now

    def _route_order(self, robot_id: str, payload: dict) -> None:
        robot = self._robots.get(robot_id)
        if robot is None:
            logger.warning("Order received for unknown robot %s", robot_id)
            return
        robot.assign_order(payload)
        logger.info("Robot %s assigned order %s", robot_id, payload.get("orderId"))

    def _route_instant_actions(self, robot_id: str, payload: dict) -> None:
        robot = self._robots.get(robot_id)
        if robot is None:
            logger.warning("InstantActions received for unknown robot %s", robot_id)
            return
        for action in payload.get("actions", []) or []:
            self._apply_action(robot, action)

    @staticmethod
    def _apply_action(robot: SimulatedRobot, action: dict) -> None:
        action_type = str(action.get("actionType", "")).upper()
        params = {p.get("key", ""): p.get("value") for p in action.get("actionParameters", []) or []}

        if action_type == "STOPPAUSE" or action_type == "HOLD":
            robot.hold()
        elif action_type == "RESUME" or action_type == "CANCELORDER":
            robot.resume()
            if action_type == "CANCELORDER":
                robot.cancel_order()
        elif action_type == "INSTANTVELOCITY":
            # Handle max_speed (speed cap) and linear_x (direction) independently.
            # Both can be present in the same action; max_speed acts as an upper
            # bound, while linear_x determines forward/retreat behaviour.
            if "max_speed" in params:
                robot.set_speed_cap(float(params["max_speed"]))
            if "linear_x" in params:
                linear_x = float(params["linear_x"])
                if linear_x < 0:
                    # Retreat: negative linear velocity. Keep it simple — hold.
                    robot.hold("retreat")
                elif linear_x > 0 and not robot.held:
                    # Forward velocity requested and robot is not held — resume.
                    robot.resume()
        elif action_type == "TRAFFICLIGHT":
            color = str(params.get("color", "")).upper()
            if color == "GREEN":
                robot.resume()
            else:
                robot.hold(f"traffic_light_{color}")

    def set_command_handlers(
        self,
        on_order: Callable[[str, dict], None] | None = None,
        on_instant_actions: Callable[[str, dict], None] | None = None,
    ) -> None:
        """Override command routing (useful for tests)."""
        if on_order is not None:
            self._route_order = on_order
        if on_instant_actions is not None:
            self._route_instant_actions = on_instant_actions

    def load_scenario(self, name: str) -> list[str]:
        """Load a named scenario configuration and return created robot IDs.

        Supported scenarios:
        - ``"intersection"``: 3 robots converging at X1, exercise traffic light gating
        - ``"charger"``: 5 low-battery robots competing for 2 charger bays
        - ``"fault"``: 1 robot that gets an injected error mid-task
        - ``"deadlock"``: 2 robots facing each other on a corridor
        - ``"safe_distance"``: 2 following robots exercising SPEED_CAP
        """
        from core.platform.fixed_lane_map import FixedLaneMap, Lane

        robot_ids: list[str] = []
        fmap = self.lane_graph._fmap
        if name == "intersection":
            fmap.add_lane(Lane("L_A_B", "A", "B", length=2.0, max_speed=1.5, intersection_id="X1", direction=0))
            fmap.add_lane(Lane("L_X_B", "X", "B", length=20.0, max_speed=1.5, intersection_id="X1", direction=0))
            fmap.add_lane(Lane("L_Y_B", "Y", "B", length=30.0, max_speed=1.5, intersection_id="X1", direction=1))
            fmap.add_lane(Lane("L_B_Z1", "B", "Z1", length=20.0, max_speed=1.5))
            fmap.add_lane(Lane("L_B_Z2", "B", "Z2", length=20.0, max_speed=1.5))
            fmap.add_lane(Lane("L_B_Z3", "B", "Z3", length=20.0, max_speed=1.5))
            for rid, lane in [("R-001", "L_A_B"), ("R-002", "L_X_B"), ("R-003", "L_Y_B")]:
                self.add_robot(rid, lane)
                robot_ids.append(rid)
        elif name == "charger":
            fmap.add_lane(Lane("L_A_B", "A", "B", length=5.0, max_speed=1.5))
            fmap.add_lane(Lane("L_B_CHG1", "B", "CHG1", length=5.0, max_speed=1.5, charger=True))
            fmap.add_lane(Lane("L_B_CHG2", "B", "CHG2", length=5.0, max_speed=1.5, charger=True))
            for i in range(1, 6):
                rid = f"R-{i:03d}"
                self.add_robot(rid, "L_A_B", battery=21.0, config=RobotConfig(max_speed=0.5))
                robot_ids.append(rid)
        elif name == "fault":
            fmap.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5))
            fmap.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=1.5))
            self.add_robot("R-001", "L_A_B")
            robot_ids.append("R-001")
        elif name == "deadlock":
            fmap.add_lane(Lane("L_A_B", "A", "B", length=10.0, max_speed=1.5, intersection_id="X1", direction=0))
            fmap.add_lane(Lane("L_B_A", "B", "A", length=10.0, max_speed=1.5, intersection_id="X1", direction=1))
            self.add_robot("R-001", "L_A_B")
            self.add_robot("R-002", "L_B_A")
            robot_ids.extend(["R-001", "R-002"])
        elif name == "safe_distance":
            fmap.add_lane(Lane("L_A_B", "A", "B", length=50.0, max_speed=2.0))
            fmap.add_lane(Lane("L_B_C", "B", "C", length=10.0, max_speed=2.0))
            self.add_robot("R-001", "L_A_B", config=RobotConfig(max_speed=1.0))
            self.add_robot("R-002", "L_A_B", config=RobotConfig(max_speed=0.5))
            robot_ids.extend(["R-001", "R-002"])
        else:
            raise ValueError(
                f"Unknown scenario: {name}. "
                "Available: intersection, charger, fault, deadlock, safe_distance"
            )
        return robot_ids

    @classmethod
    def for_scenario(
        cls,
        name: str,
        brand: str = "generic",
        mqtt_client: MqttVDAClient | None = None,
        publish_interval: float = 0.5,
    ) -> "FleetSimulator":
        """Factory: create a FleetSimulator pre-configured for a named test scenario.

        Builds an in-memory lane graph, creates the simulator, and adds robots
        at scenario-appropriate positions with correct battery levels.

        Supported scenarios:
          - ``"intersection"``  — 3 robots converging on a 3-way intersection
          - ``"charger"``       — 2 robots, 1 charger bay, one at 15 % battery
          - ``"fault"``         — 1 robot with scheduled fault injection
          - ``"deadlock"``      — 2 robots facing each other on a single lane
          - ``"safe_distance"`` — 2 robots following each other on a linear path
        """
        from core.platform.fixed_lane_map import FixedLaneMap, Lane

        fmap = FixedLaneMap()

        if name == "intersection":
            lanes_def = [
                ("L_A_X", "A", "X", 10.0),
                ("L_B_X", "B", "X", 10.0),
                ("L_C_X", "C", "X", 10.0),
                ("L_X_D", "X", "D", 10.0),
            ]
        elif name == "charger":
            lanes_def = [
                ("L_A_B", "A", "B", 10.0),
                ("L_B_A", "B", "A", 10.0),
            ]
        elif name == "fault":
            lanes_def = [
                ("L_A_B", "A", "B", 10.0),
                ("L_B_C", "B", "C", 10.0),
            ]
        elif name == "deadlock":
            lanes_def = [
                ("L_A_B", "A", "B", 10.0),
                ("L_B_A", "B", "A", 10.0),
            ]
        elif name == "safe_distance":
            lanes_def = [
                ("L_A_B", "A", "B", 10.0),
                ("L_B_C", "B", "C", 10.0),
            ]
        else:
            raise ValueError(
                f"Unknown scenario {name!r}; "
                f"choices: intersection, charger, fault, deadlock, safe_distance"
            )

        for lid, frm, to, length in lanes_def:
            lane = Lane(
                lane_id=lid,
                from_node=frm,
                to_node=to,
                length=length,
                max_speed=1.0,
                charger=(name == "charger" and lid == "L_B_A"),
            )
            fmap.add_lane(lane)

        lane_graph = LaneGraph(fmap)
        sim = cls(
            lane_graph=lane_graph,
            brand=brand,
            mqtt_client=mqtt_client,
            publish_interval=publish_interval,
        )

        if name == "intersection":
            sim.add_robot("R-001", start_lane="L_A_X", battery=100.0)
            sim.add_robot("R-002", start_lane="L_B_X", battery=100.0)
            sim.add_robot("R-003", start_lane="L_C_X", battery=100.0)
        elif name == "charger":
            sim.add_robot("R-001", start_lane="L_A_B", battery=15.0)
            sim.add_robot("R-002", start_lane="L_A_B", battery=80.0)
        elif name == "fault":
            sim.add_robot("R-001", start_lane="L_A_B", battery=100.0)
        elif name == "deadlock":
            sim.add_robot("R-001", start_lane="L_A_B", battery=100.0)
            sim.add_robot("R-002", start_lane="L_B_A", battery=100.0)
        elif name == "safe_distance":
            sim.add_robot("R-001", start_lane="L_A_B", battery=100.0)
            sim.add_robot("R-002", start_lane="L_A_B", battery=100.0)

        return sim

    @property
    def robot_ids(self) -> list[str]:
        return list(self._robots.keys())
