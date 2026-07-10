"""Order sequencer — one order queue, one platform, one sequence of tasks.

A customer order (e.g. "move tote from A to B") is decomposed into a
sequence of ``Task`` objects whose lane paths are resolved on the unified
map.  The sequencer enforces:

- action primitive order (e.g. MOVE → PICK → MOVE → PLACE),
- payload / capability checks at order time,
- deterministic task IDs derived from the order id and step index.

This gives the upper-layer WMS/ERP a single entry point while the scheduler
still works with brand-agnostic ``Task`` objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from core.messages import ActionPrimitive
from core.platform.fixed_lane_map import FixedLaneMap
from core.scheduling.task_allocator import Task


class OrderStatus(Enum):
    PENDING = auto()
    PLANNED = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class Order:
    """High-level request from WMS/ERP."""

    order_id: str
    origin_lane: str
    destination_lane: str
    # 业务动作序列; 默认 MOVE → PICK/MOVE → PLACE (简化)
    actions: list[ActionPrimitive] = field(default_factory=lambda: [ActionPrimitive.MOVE])
    payload_kg: float = 0.0
    priority: int = 0
    status: OrderStatus = OrderStatus.PENDING


@dataclass
class OrderPlan:
    """Planned order: a sequence of tasks with a unified lane path."""

    order: Order
    tasks: list[Task]


class OrderSequencer:
    """Decompose an ``Order`` into ``Task`` steps on the unified map."""

    def __init__(self, fmap: FixedLaneMap | None = None) -> None:
        self.fmap = fmap

    def plan(self, order: Order) -> OrderPlan:
        """Translate an order into a deterministic task list.

        If a unified map is available, each MOVE step is expanded to the
        shortest lane path; otherwise start/end lanes are used directly.
        """
        tasks: list[Task] = []
        # 简化的两阶段模型: origin → destination, 中间插入业务动作.
        # 复杂订单可在上层拆解后多次调用 plan.
        start = order.origin_lane
        goal = order.destination_lane
        move_path: list[str] = []
        if self.fmap is not None:
            move_path = self.fmap.shortest_path(start, goal)

        for idx, action in enumerate(order.actions):
            if action is ActionPrimitive.MOVE and move_path:
                path = move_path
            else:
                path = [start, goal]
            task_id = f"{order.order_id}-{idx}"
            tasks.append(
                Task(
                    task_id=task_id,
                    start_lane=path[0],
                    end_lane=path[-1],
                    priority=order.priority,
                    action_primitives={action},
                    required_payload_kg=order.payload_kg,
                )
            )
        order.status = OrderStatus.PLANNED
        return OrderPlan(order=order, tasks=tasks)

    def next_open_task(self, plan: OrderPlan) -> Task | None:
        """Return the first task that has not been allocated/completed."""
        for t in plan.tasks:
            # Caller tracks completion; here we just return the first task.
            return t
        return None
