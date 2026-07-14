"""三层次冲突空间协调器 (v7 Phase 4 task 1).

v7 架构说明书: 冲突层空间三层次 —
    L1 宏观区块路由 → L2 区块内 ECBS 车道图 MAPF → L3 路口信号灯

本模块把已有的三个独立组件 *接线* 为一条协调管线, 而非重写任一层:
  - L1 宏观: 计算每车走廊 (FixedLaneMap.shortest_path), 按 *共享节点* 把
    请求分成交互组 — 非交互组各自独立 solve, 不进同一 ECBS (O(n²) 冲突检测
    只在交互组内付出). 过度分组 (over-group) 安全, 漏分组 (under-group) 是 bug.
  - L2 区块内: 每个交互组喂 MAPFEngine.solve — ECBS 顶点/边冲突 + 时间窗.
  - L3 路口: 计划中穿越路口车道 (Lane.intersection_id) 的 move, 经
    TrafficLightController.may_enter 门控 — 红/黄灯须 wait, 绿灯放行.

信号灯 FSM (GREEN→YELLOW 3s→RED) 已在 traffic_light_controller 实现, 本处
不重复. ``coordinate`` 不 tick 灯 (由平台循环驱动); 仅读当前灯态门控.

# ponytail: L3 仅 *标注* 受阻 move (IntersectionGate), 不做时间平移重排 —
# 平移会与它车再冲突, 须带 wait 约束重跑 ECBS. 升级路径: gate→constraint
# 反馈进 ECBS 重解 (滚动窗口已支持 incremental update).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.platform.fixed_lane_map import FixedLaneMap, Lane
from core.scheduling.mapf_engine import AgentRequest, MAPFEngine, Plan
from core.scheduling.traffic_light_controller import TrafficLightController


@dataclass(frozen=True)
class IntersectionGate:
    """L3 路口门控决策: 该 move 是否允许进入路口."""

    agent_id: str
    intersection_id: str
    direction: int
    move_index: int
    allowed: bool


@dataclass
class ConflictResolution:
    """三层次协调结果."""

    plans: dict[str, Plan] = field(default_factory=dict)
    groups: list[list[str]] = field(default_factory=list)  # agent_ids per L1 组
    gates: list[IntersectionGate] = field(default_factory=list)
    ecbs_group_count: int = 0  # 需 ECBS 的组数 (≥2 车)

    def get(self, agent_id: str) -> Plan | None:
        return self.plans.get(agent_id)

    def blocked_gates(self) -> list[IntersectionGate]:
        """须 wait 的路口门控 (红灯/黄灯)."""
        return [g for g in self.gates if not g.allowed]


class ConflictLayerCoordinator:
    """L1 宏观 → L2 ECBS → L3 路口灯 协调管线."""

    def __init__(
        self,
        fmap: FixedLaneMap,
        mapf: MAPFEngine,
        tlc: TrafficLightController,
    ) -> None:
        self.fmap = fmap
        self.mapf = mapf
        self.tlc = tlc

    # ── 公共入口 ───────────────────────────────────────────────
    def coordinate(
        self, requests: list[AgentRequest], now: float = 0.0
    ) -> ConflictResolution:
        if not requests:
            return ConflictResolution()

        # L1 宏观: 走廊 + 交互组
        corridors = {r.agent_id: self._corridor_nodes(r) for r in requests}
        groups = self._macro_groups([r.agent_id for r in requests], corridors)
        req_by_id = {r.agent_id: r for r in requests}

        # L2 区块内: 每组独立 ECBS
        plans: dict[str, Plan] = {}
        ecbs_groups = 0
        for group in groups:
            grp_reqs = [req_by_id[aid] for aid in group]
            if len(grp_reqs) > 1:
                ecbs_groups += 1
            sol = self.mapf.solve(grp_reqs)
            plans.update(sol.plans)

        # L3 路口门控
        gates = self._gate_intersections(plans)

        return ConflictResolution(
            plans=plans,
            groups=groups,
            gates=gates,
            ecbs_group_count=ecbs_groups,
        )

    # ── L1 宏观 ────────────────────────────────────────────────
    def _corridor_nodes(self, req: AgentRequest) -> set[str]:
        """请求走廊的节点集 (用于交互分组)."""
        lane_filter = self._model_filter(req.model)
        lane_path = self.fmap.shortest_path(req.start, req.goal, lane_filter=lane_filter)
        nodes: set[str] = {req.start, req.goal}
        for lid in lane_path:
            lane = self.fmap.lane(lid)
            if lane is not None:
                nodes.add(lane.from_node)
                nodes.add(lane.to_node)
        return nodes

    @staticmethod
    def _model_filter(model: str):
        if not model:
            return None
        return lambda lane: lane.allows_model(model)

    @staticmethod
    def _macro_groups(
        agent_ids: list[str], corridors: dict[str, set[str]]
    ) -> list[list[str]]:
        """按共享走廊节点分组 (union-find). 非交互 → 各自单元素组."""
        parent: dict[str, str] = {a: a for a in agent_ids}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i, a in enumerate(agent_ids):
            for b in agent_ids[i + 1 :]:
                if corridors[a] & corridors[b]:
                    union(a, b)

        comp: dict[str, list[str]] = {}
        for a in agent_ids:
            comp.setdefault(find(a), []).append(a)
        # 稳定排序: 组内按 agent_id, 组间按首元素
        groups = [sorted(members) for members in comp.values()]
        groups.sort(key=lambda g: g[0])
        return groups

    # ── L3 路口门控 ────────────────────────────────────────────
    def _gate_intersections(self, plans: dict[str, Plan]) -> list[IntersectionGate]:
        gates: list[IntersectionGate] = []
        for agent_id, plan in plans.items():
            for idx, move in enumerate(plan.moves):
                if move.lane_id is None:
                    continue  # WAIT move
                lane = self.fmap.lane(move.lane_id)
                if lane is None or lane.intersection_id is None:
                    continue
                allowed = self.tlc.may_enter(lane.intersection_id, lane.direction)
                gates.append(
                    IntersectionGate(
                        agent_id=agent_id,
                        intersection_id=lane.intersection_id,
                        direction=lane.direction,
                        move_index=idx,
                        allowed=allowed,
                    )
                )
        return gates


# ── 自检 (DoD: 三层次接线 — 交互组进 ECBS, 非交互独立, 路口红门门控) ──
def _demo() -> None:
    fmap = FixedLaneMap()
    # 两条独立走廊: A-B-C 与 D-E-F, 在 X 路口 (C 节点) 无交集
    fmap.add_lane(Lane("L1", "A", "B", length=3.0))
    fmap.add_lane(Lane("L2", "B", "C", length=3.0))
    fmap.add_lane(Lane("L3", "D", "E", length=3.0))
    fmap.add_lane(Lane("L4", "E", "F", length=3.0))
    # 路口车道: C -> G 经路口 IX (方向 0)
    fmap.add_lane(Lane("LX", "C", "G", length=2.0, intersection_id="IX", direction=0))

    mapf = MAPFEngine(fmap, time_horizon=20)
    tlc = TrafficLightController()
    tlc.register("IX")  # 默认 RED
    coord = ConflictLayerCoordinator(fmap, mapf, tlc)

    reqs = [
        AgentRequest("R1", "A", "C", priority=0),
        AgentRequest("R2", "A", "C", priority=1),  # 与 R1 共享走廊 → 同组 → ECBS
        AgentRequest("R3", "D", "F", priority=0),  # 独立走廊 → 单元素组
        AgentRequest("R4", "A", "G", priority=0),  # 穿越路口 IX (C→G) → L3 门控
    ]
    res = coord.coordinate(reqs)

    # L1: R1,R2,R4 共享 A-B-C 走廊 → 同组; R3 独立
    assert any({"R1", "R2", "R4"} <= set(g) for g in res.groups), "R1,R2,R4 must group"
    assert res.ecbs_group_count == 1, "exactly one ECBS group"
    # L2: 四车都有 plan
    assert all(res.get(a) is not None for a in ("R1", "R2", "R3", "R4"))
    # L3: R4 穿越路口 IX, 灯 RED → 门控 blocked
    blocked = res.blocked_gates()
    assert blocked, "R4 must be gated at RED intersection IX"
    assert all(g.intersection_id == "IX" for g in blocked)
    print(
        f"OK: 3-layer coord — {len(res.groups)} groups, "
        f"{res.ecbs_group_count} ECBS, {len(blocked)} gated"
    )


if __name__ == "__main__":
    _demo()
