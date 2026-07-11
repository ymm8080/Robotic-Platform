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
        """Start the optional real-time tick thread.

        The caller is responsible for calling ``mqtt_client.connect()`` and
        publishing initial connection messages before calling this method.
        """
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
            # Only wait when there's positive sleep time remaining.
            # If both schedules are overdue (sleep_dur <= 0), skip waiting
            # to avoid busy-waiting on wait(0) and process immediately.
            if sleep_dur > 0:
                self._stop_event.wait(sleep_dur)

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
            if "max_speed" in params:
                robot.set_speed_cap(float(params["max_speed"]))
            elif "linear_x" in params:
                # Retreat: negative linear velocity. Keep it simple — hold.
                if float(params["linear_x"]) < 0:
                    robot.hold("retreat")
                else:
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

    @property
    def robot_ids(self) -> list[str]:
        return list(self._robots.keys())
