"""Fixed Lane Map — 图层化地图 (陷阱 #6: 地图语义腐蚀; v4.0 §5.3).

Two layers (白皮书陷阱 #6 补丁: 物理层 + 语义覆盖层):
  - physical:  lanes, intersections, chargers, lifts (rarely changes;
               change requires Ground Truth 校验 + 签字, 附录A.7).
  - semantic:  temporary overlays — virtual walls, blocked lanes,
               dynamic obstacles with confidence decay (volatile, never
               mutates physical).

v4.0 补丁3 / §5.3 additions:
  - 车道边属性: allowed_models / max_speed / max_grade / floor_threshold /
    no_reverse (不可倒车路段必须在 nav graph 中明确标记).
  - 动态障碍物置信度衰减: 每5s×0.7, <0.3 自动擦除.
  - 交叉验证: 动态障碍物必须被至少2台不同品牌机器人观测到, 或连续3个周期
    稳定存在 (离群点剔除 — 单机噪点直接丢弃, 不广播).
  - 机器人无权直接写地图, 只能上报观测证据 (report_observation).

GitHub: rmf_traffic_editor (https://github.com/open-rmf/rmf_traffic_editor)
        — 导航图编辑器, 改造为车道图.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from core.messages import EnvConstraints


class SpeedClass(str, Enum):
    FAST = "FAST"
    SLOW = "SLOW"


@dataclass
class Lane:
    """单向车道 (v4.0 §3.3). 每条车道单向, 宽度固定 (如 1.2m)."""

    lane_id: str
    from_node: str
    to_node: str
    length: float                       # metres
    width: float = 1.2                  # 固定宽度
    speed_class: SpeedClass = SpeedClass.FAST
    # v4.0 补丁3: 车道通行能力 (边属性)
    allowed_models: list[str] = field(default_factory=list)  # 允许通行型号, 空=不限
    max_speed: float = 1.5              # 车道最大速度
    env: EnvConstraints = field(default_factory=EnvConstraints)
    no_reverse: bool = False            # 不可倒车路段 (nav graph 明确标记)
    charger: bool = False
    lift_id: str | None = None
    floor: int | None = None            # 楼层, 用于电梯预约
    # 路口信号灯关联 (可选): 属于哪个路口的哪个方向
    intersection_id: str | None = None
    direction: int = 0

    def allows_model(self, model: str) -> bool:
        return not self.allowed_models or model in self.allowed_models

    def allows_any(self, models: list[str]) -> bool:
        """True if the lane is open to at least one of ``models`` (or unrestricted)."""
        if not self.allowed_models:
            return True
        return any(m in self.allowed_models for m in models)


@dataclass
class DynamicObstacle:
    """动态障碍物观测 (v4.0 §5.3). 置信度衰减 + 交叉验证."""

    x: float
    y: float
    confidence: float = 1.0
    observers: set[str] = field(default_factory=set)   # 观测到的 robot_id 集合
    brands: set[str] = field(default_factory=set)       # 观测品牌 (交叉验证用)
    stable_cycles: int = 0
    last_seen: float = 0.0


@dataclass
class SemanticOverlay:
    """临时语义覆盖层 — 不腐蚀物理层."""

    blocked_lanes: set[str] = field(default_factory=set)
    virtual_walls: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y, r)
    dynamic_obstacles: dict[tuple[float, float], DynamicObstacle] = field(default_factory=dict)


class FixedLaneMap:
    """Layered map: physical (immutable-ish) + semantic (volatile)."""

    # v4.0 §5.3: 每5s×0.7, <0.3 自动擦除
    DECAY_INTERVAL = 5.0
    DECAY_FACTOR = 0.7
    ERASE_THRESHOLD = 0.3
    # 交叉验证: 至少2台不同品牌, 或连续3个周期稳定
    CROSS_VALIDATE_BRANDS = 2
    CROSS_VALIDATE_CYCLES = 3

    def __init__(self) -> None:
        self._lanes: dict[str, Lane] = {}
        self._adjacency: dict[str, list[str]] = {}
        self.overlay = SemanticOverlay()
        self._occupancy: dict[str, str] = {}  # lane_id -> robot_id

    # ── lane occupancy ─────────────────────────────────────────
    def occupy_lane(self, lane_id: str, robot_id: str) -> None:
        if lane_id in self._lanes:
            self._occupancy[lane_id] = robot_id

    def vacate_lane(self, lane_id: str, robot_id: str) -> None:
        if self._occupancy.get(lane_id) == robot_id:
            self._occupancy.pop(lane_id, None)

    def lane_occupant(self, lane_id: str) -> str | None:
        return self._occupancy.get(lane_id)

    def occupied_lanes(self) -> dict[str, str]:
        return dict(self._occupancy)

    # ── physical layer ─────────────────────────────────────────
    def add_lane(self, lane: Lane) -> None:
        self._lanes[lane.lane_id] = lane
        self._adjacency.setdefault(lane.from_node, []).append(lane.lane_id)

    def lane(self, lane_id: str) -> Lane | None:
        return self._lanes.get(lane_id)

    def lanes_out_of(self, node: str) -> list[str]:
        return list(self._adjacency.get(node, []))

    def chargers(self) -> list[str]:
        return [lane.lane_id for lane in self._lanes.values() if lane.charger]

    def all_lanes(self) -> list[Lane]:
        return list(self._lanes.values())

    def no_reverse_lanes(self) -> list[str]:
        """不可倒车路段 (Adapter 硬编码后退前提, v4.0 §5.4)."""
        return [lane.lane_id for lane in self._lanes.values() if lane.no_reverse]

    # ── map validation (灰犀牛 #12 验收陷阱) ─────────────────────
    def validate(self) -> list[str]:
        """Return a list of integrity warnings; empty list means map is healthy."""
        issues: list[str] = []
        if not self._lanes:
            issues.append("map has no lanes")
            return issues
        nodes = set()
        for lane in self._lanes.values():
            nodes.add(lane.from_node)
            nodes.add(lane.to_node)
            if lane.length <= 0:
                issues.append(f"lane {lane.lane_id} has non-positive length")
            if lane.max_speed <= 0:
                issues.append(f"lane {lane.lane_id} has non-positive max_speed")
            if lane.width <= 0:
                issues.append(f"lane {lane.lane_id} has non-positive width")
        # connectivity: every node should be reachable from every other node
        # (weakly connected for a single facility)
        if nodes:
            start = next(iter(nodes))
            reachable = self._reachable_nodes(start)
            unreachable = nodes - reachable
            for node in sorted(unreachable):
                issues.append(f"node {node} is unreachable from {start}")
        return issues

    def _reachable_nodes(self, start: str) -> set[str]:
        """BFS over the undirected lane graph."""
        visited: set[str] = {start}
        frontier = [start]
        while frontier:
            node = frontier.pop()
            # forward lanes
            for lid in self._adjacency.get(node, []):
                lane = self._lanes.get(lid)
                if lane is None:
                    continue
                if lane.to_node not in visited:
                    visited.add(lane.to_node)
                    frontier.append(lane.to_node)
            # backward lanes
            for lane in self._lanes.values():
                if lane.to_node == node and lane.from_node not in visited:
                    visited.add(lane.from_node)
                    frontier.append(lane.from_node)
        return visited

    # ── semantic layer (volatile) ──────────────────────────────
    def block_lane(self, lane_id: str) -> None:
        self.overlay.blocked_lanes.add(lane_id)

    def unblock_lane(self, lane_id: str) -> None:
        self.overlay.blocked_lanes.discard(lane_id)

    def add_virtual_wall(self, x: float, y: float, radius: float) -> None:
        self.overlay.virtual_walls.append((x, y, radius))

    def is_traversable(self, lane_id: str) -> bool:
        return lane_id in self._lanes and lane_id not in self.overlay.blocked_lanes

    # ── dynamic obstacles: 置信度衰减 + 交叉验证 (v4.0 §5.3) ────
    def report_observation(
        self, x: float, y: float, robot_id: str, brand: str, now: float
    ) -> bool:
        """机器人无权直接写地图, 只能上报观测证据.

        Returns True iff the observation survives cross-validation and is
        accepted into the overlay (广播给其他机器人). 单机噪点 → 丢弃.
        """
        key = (round(x, 2), round(y, 2))
        obs = self.overlay.dynamic_obstacles.get(key)
        if obs is None:
            obs = DynamicObstacle(x=x, y=y, confidence=1.0, last_seen=now)
            self.overlay.dynamic_obstacles[key] = obs
        obs.observers.add(robot_id)
        if brand:
            obs.brands.add(brand)
        obs.last_seen = now
        obs.stable_cycles += 1
        obs.confidence = 1.0  # fresh observation refreshes confidence
        return self._is_confirmed(obs)

    def _is_confirmed(self, obs: DynamicObstacle) -> bool:
        """交叉验证: ≥2 不同品牌 或 连续3周期稳定."""
        return (
            len(obs.brands) >= self.CROSS_VALIDATE_BRANDS
            or obs.stable_cycles >= self.CROSS_VALIDATE_CYCLES
        )

    def confirmed_obstacles(self) -> list[DynamicObstacle]:
        """仅返回通过交叉验证的障碍物 (可广播)."""
        return [o for o in self.overlay.dynamic_obstacles.values() if self._is_confirmed(o)]

    def decay_obstacles(self, now: float) -> list[tuple[float, float]]:
        """每5s×0.7 衰减, <0.3 自动擦除. Returns erased keys."""
        erased: list[tuple[float, float]] = []
        for key, obs in list(self.overlay.dynamic_obstacles.items()):
            if now - obs.last_seen >= self.DECAY_INTERVAL:
                obs.confidence *= self.DECAY_FACTOR
                obs.last_seen = now
                if obs.confidence < self.ERASE_THRESHOLD:
                    erased.append(key)
                    del self.overlay.dynamic_obstacles[key]
        return erased

    def distance(self, lane_a: str, lane_b: str) -> float:
        """Heuristic lane-to-lane distance for the TaskAllocator utility.

        Deprecated: use ``distance_between`` for graph-aware distance.
        """
        la = self._lanes.get(lane_a)
        if la is None:
            return 1.0
        return la.length

    def shortest_path(
        self,
        start: str,
        goal: str,
        lane_filter: Callable[[Lane], bool] | None = None,
        cost: str = "length",
    ) -> list[str]:
        """Return lane-id shortest path from ``start`` to ``goal`` (Dijkstra).

        ``start`` and ``goal`` may be node ids or lane ids.  If lane ids are
        passed, the path begins/ends with that lane.

        ``lane_filter(lane)`` may be supplied to enforce robot-specific
        constraints (model, env, no_reverse).

        ``cost`` may be ``"length"`` (metres) or ``"time"`` (seconds at lane
        max_speed).
        """
        import heapq

        def _to_node(ref: str) -> str:
            lane = self._lanes.get(ref)
            return lane.from_node if lane else ref

        def _from_node(ref: str) -> str:
            lane = self._lanes.get(ref)
            return lane.to_node if lane else ref

        def _allowed(lane: Lane) -> bool:
            if lane_filter is None:
                return True
            try:
                return bool(lane_filter(lane))
            except Exception:  # noqa: BLE001
                return False

        def _lane_cost(lane: Lane) -> float:
            if cost == "time":
                return lane.length / lane.max_speed if lane.max_speed > 0 else float("inf")
            return lane.length

        start_node = _to_node(start)
        goal_node = _from_node(goal)
        if start_node == goal_node and start != goal:
            lane = self._lanes.get(start)
            if lane and lane.to_node == goal_node and _allowed(lane):
                return [start]

        first_lanes = [
            lid
            for lid in self._lanes
            if self._lanes[lid].from_node == start_node and _allowed(self._lanes[lid])
        ]
        if not first_lanes and start in self._lanes and _allowed(self._lanes[start]):
            first_lanes = [start]
        heap: list[tuple[float, str, list[str]]] = []
        for lid in first_lanes:
            heapq.heappush(heap, (_lane_cost(self._lanes[lid]), lid, [lid]))
        visited: set[str] = set()
        while heap:
            cur_cost, lane_id, path = heapq.heappop(heap)
            lane = self._lanes.get(lane_id)
            if lane is None or not _allowed(lane):
                continue
            node = lane.to_node
            if node == goal_node:
                return path
            if node in visited:
                continue
            visited.add(node)
            for next_id in self._adjacency.get(node, []):
                if next_id in path:
                    continue
                next_lane = self._lanes[next_id]
                if not _allowed(next_lane):
                    continue
                heapq.heappush(
                    heap,
                    (cur_cost + _lane_cost(next_lane), next_id, path + [next_id]),
                )
        return []

    def distance_between(
        self,
        a: str,
        b: str,
        lane_filter: Callable[[Lane], bool] | None = None,
        cost: str = "length",
    ) -> float:
        """Graph-aware cost from ``a`` to ``b`` (lane ids or node ids)."""
        path = self.shortest_path(a, b, lane_filter=lane_filter, cost=cost)
        if cost == "time":
            return sum(self._lanes[lid].length / self._lanes[lid].max_speed for lid in path if self._lanes[lid].max_speed > 0) or 1.0
        return sum(self._lanes[lid].length for lid in path) or 1.0

    # ── Ground Truth (附录A.7, 灰犀牛 #12 验收陷阱) ────────────
    def ground_truth_checksum(self) -> int:
        """Cheap checksum of the physical layer for change detection."""
        return hash(tuple(sorted(
            (lane.lane_id, lane.from_node, lane.to_node, lane.length, lane.speed_class.value)
            for lane in self._lanes.values()
        )))
