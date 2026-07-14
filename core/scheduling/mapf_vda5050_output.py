"""Convert a MAPFEngine solution into VDA5050 orders + zone reservations.

Phase 3 of the v7.0 plan (§Phase 3 task 7):

    输出 = 每车"车道序列 + 节点时间窗预约"，下发为 VDA5050 order
    （nodes+edges）+ zones 预订。

The platform plans **topology + time-window reservations only**. This module
turns a :class:`~core.scheduling.mapf_engine.Plan` (a sequence of
WAIT/TRAVERSE moves over the lane graph) into:

* a **VDA5050 order** — ``nodes`` (the visited node sequence) + ``edges`` (the
  traversed lanes, each linking its start/end node), and
* a **zone reservation list** — per-node time-window bookings derived from the
  plan's vertex occupancy, used by the conflict layer to enforce reservations.

It does **not** generate metric trajectories (x/y are taken from an optional
``node_coords`` map; absent coordinates default to 0,0 since the platform does
not own metric driving — that is the FMS's job, plan §边界).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.scheduling.mapf_engine import Plan, Solution

# Re-exported for callers that build orders without a full Solution.
__all__ = [
    "VDA5050Node",
    "VDA5050Edge",
    "VDA5050Order",
    "ZoneReservation",
    "plan_to_order",
    "plan_to_zones",
    "solution_to_orders",
    "solution_to_zones",
]


@dataclass
class VDA5050Node:
    node_id: str
    sequence_id: int
    x: float = 0.0
    y: float = 0.0
    released: bool = True
    actions: list[dict] = field(default_factory=list)


@dataclass
class VDA5050Edge:
    edge_id: str
    start_node_id: str
    end_node_id: str
    sequence_id: int
    lane_id: str | None = None
    released: bool = True
    action: str | None = None


@dataclass
class VDA5050Order:
    order_id: str
    order_update_id: int = 0
    nodes: list[VDA5050Node] = field(default_factory=list)
    edges: list[VDA5050Edge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "orderId": self.order_id,
            "orderUpdateId": self.order_update_id,
            "nodes": [
                {
                    "nodeId": n.node_id,
                    "sequenceId": n.sequence_id,
                    "x": n.x,
                    "y": n.y,
                    "released": n.released,
                    "actions": n.actions,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "edgeId": e.edge_id,
                    "startNodeId": e.start_node_id,
                    "endNodeId": e.end_node_id,
                    "sequenceId": e.sequence_id,
                    "released": e.released,
                    "action": e.action,
                }
                for e in self.edges
            ],
        }


@dataclass
class ZoneReservation:
    """A node time-window reservation for one vehicle."""

    node_id: str
    robot_id: str
    start_time: int  # timestep (seconds) from plan origin
    end_time: int  # inclusive timestep

    def to_dict(self) -> dict:
        return {
            "nodeId": self.node_id,
            "robotId": self.robot_id,
            "startTime": self.start_time,
            "endTime": self.end_time,
        }


def _ordered_visited_nodes(plan: Plan) -> list[str]:
    """Node visit sequence, collapsing consecutive WAITs at the same node."""
    visited: list[str] = []
    current: str | None = None
    for m in plan.moves:
        if m.from_node != current:
            visited.append(m.from_node)
            current = m.from_node
        if not m.is_wait and m.to_node != current:
            visited.append(m.to_node)
            current = m.to_node
    if not visited:
        visited = [plan.moves[0].from_node] if plan.moves else []
    return visited


def plan_to_order(
    plan: Plan,
    order_id: str | None = None,
    order_update_id: int = 0,
    node_coords: dict[str, tuple[float, float]] | None = None,
) -> VDA5050Order:
    """Convert a single :class:`Plan` into a VDA5050 order.

    ``node_coords`` optionally maps node id → (x, y) for the order's node
    coordinates. Nodes without a coordinate default to (0, 0).
    """
    oid = order_id or f"order-{plan.agent_id}"
    coords = node_coords or {}
    nodes_seq = _ordered_visited_nodes(plan)

    vnodes: list[VDA5050Node] = []
    for seq, nid in enumerate(nodes_seq):
        x, y = coords.get(nid, (0.0, 0.0))
        vnodes.append(VDA5050Node(node_id=nid, sequence_id=seq, x=x, y=y))

    vedges: list[VDA5050Edge] = []
    edge_seq = 0
    for m in plan.moves:
        if m.is_wait:
            continue
        vedges.append(
            VDA5050Edge(
                edge_id=f"{m.lane_id or m.from_node + '-' + m.to_node}-{edge_seq}",
                start_node_id=m.from_node,
                end_node_id=m.to_node,
                sequence_id=edge_seq,
                lane_id=m.lane_id,
            )
        )
        edge_seq += 1

    return VDA5050Order(
        order_id=oid,
        order_update_id=order_update_id,
        nodes=vnodes,
        edges=vedges,
    )


def plan_to_zones(plan: Plan, horizon: int | None = None) -> list[ZoneReservation]:
    """Convert a plan's vertex occupancy into contiguous zone reservations.

    Consecutive timesteps at the same node are merged into one reservation.
    If ``horizon`` is given, the goal hold is clamped to it.
    """
    if not plan.moves:
        return []
    if horizon is None:
        horizon = plan.moves[-1].arrive_time

    # reuse Plan.vertex_occupancy to avoid duplicating the occupancy logic
    occ = plan.vertex_occupancy(horizon)

    # group by node, merge contiguous runs
    by_node: dict[str, list[int]] = {}
    for node, t in occ:
        by_node.setdefault(node, []).append(t)

    reservations: list[ZoneReservation] = []
    for node, times in by_node.items():
        times.sort()
        run_start = times[0]
        prev = times[0]
        for t in times[1:]:
            if t == prev + 1:
                prev = t
            else:
                reservations.append(ZoneReservation(node, plan.agent_id, run_start, prev))
                run_start = t
                prev = t
        reservations.append(ZoneReservation(node, plan.agent_id, run_start, prev))
    return reservations


def solution_to_orders(
    solution: Solution,
    node_coords: dict[str, tuple[float, float]] | None = None,
) -> dict[str, VDA5050Order]:
    """Convert every plan in a solution to a VDA5050 order, keyed by agent id."""
    return {
        aid: plan_to_order(plan, order_id=f"order-{aid}", node_coords=node_coords)
        for aid, plan in solution.plans.items()
    }


def solution_to_zones(solution: Solution, horizon: int | None = None) -> list[ZoneReservation]:
    """Flatten all plans' zone reservations into one list."""
    zones: list[ZoneReservation] = []
    for plan in solution.plans.values():
        zones.extend(plan_to_zones(plan, horizon))
    return zones
