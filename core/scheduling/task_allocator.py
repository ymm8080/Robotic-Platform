"""Task Allocator — 贪心起步 + 信誉度加权 + 能力过滤 (陷阱 #1, v4.0 补丁3).

Implements the效用函数 reserved in Function Spec §5.1. The RaaS
cost term (γ) is wired but defaults to 0 — enabled after 3 months of
telemetry (灰犀牛 #14: 预留 cost_weight 接口, γ=0 默认).

v4.0 补丁3 (语义鸿沟) additions, applied BEFORE utility scoring:
  - 动作原语匹配: 任务描述必须包含动作原语, 不支持则直接过滤.
  - 环境约束匹配: 机器人能力向量必须能通过车道 env (爬坡度/门槛高度).
  - 车道型号匹配: 车道 allowed_models 必须包含该机器人型号.
  - 迟到惩罚: 迟到率>10% 的品牌自动增加时间惩罚 (via reputation).
  - 降级拒绝: 降级模式下的机器人不再接受新任务, 直到人工恢复.

This is the greedy allocator; it does NOT do global optimisation. The
whitepaper explicitly trades optimality for the determinism of fixed-lane
scheduling (降维打击). Rolling horizon: only the next 5s of work is
considered (陷阱 #4: 级联延迟放大 → 滚动时域, 只排未来 5s).

GitHub: rmf_task (https://github.com/open-rmf/rmf_task) — task allocation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.config import GovernanceConfig
from core.governance.economic_model import EconomicModel
from core.governance.reputation_engine import ReputationEngine
from core.messages import ActionPrimitive, CapabilityVector, FleetState, RobotMode, TaskAssignment


@dataclass
class Task:
    task_id: str
    start_lane: str
    end_lane: str
    priority: int = 0          # 0=normal, higher=urgent
    created_at: float = 0.0
    deadline: float = 0.0      # 超时未分配 → EXPIRED (Function Spec §2.1)
    # v4.0 补丁3: 动作原语 (任务描述必须包含, 不支持则过滤)
    action_primitives: set[ActionPrimitive] = field(default_factory=lambda: {ActionPrimitive.MOVE})
    required_payload_kg: float = 0.0


@dataclass
class AllocationResult:
    assigned: bool
    task_id: str
    robot_id: str | None = None
    utility: float = 0.0
    reason: str = ""


class TaskAllocator:
    """Greedy allocator with capability filtering + reputation-weighted utility."""

    LATENESS_PENALTY_THRESHOLD = 0.10  # 迟到率>10% → 时间惩罚 (v4.0 §5.2)

    def __init__(
        self,
        reputation: ReputationEngine,
        config: GovernanceConfig | None = None,
        economic_model: EconomicModel | None = None,
        distance_fn=None,
        lane_lookup=None,
        path_finder=None,
    ) -> None:
        self.reputation = reputation
        self.cfg = config or GovernanceConfig()
        self.economic = economic_model
        # distance_fn(a, b) → metres. Injected so the allocator stays
        # decoupled from the map implementation.
        self._distance = distance_fn or (lambda a, b: 1.0)
        # lane_lookup(lane_id) → Lane | None, for env/model filtering.
        self._lane = lane_lookup or (lambda _: None)
        # path_finder(start_lane, end_lane) → list[lane_id]; if None the
        # assignment keeps only start/end.
        self._path_finder = path_finder

    # ── v4.0 补丁3: capability filtering (before utility) ───────
    def can_execute(self, robot: FleetState, task: Task) -> tuple[bool, str]:
        """Filter BEFORE utility. "载重50kg" 不代表能过 3 号区门槛."""
        cap = robot.capability
        if task.required_payload_kg > cap.payload_kg:
            return False, "payload_exceeds"
        if not cap.supports(task.action_primitives):
            return False, "action_primitive_unsupported"
        # 环境约束 + 型号: 检查起点和终点车道
        if not self._lane_fits(robot, cap, task.start_lane):
            return False, "start_lane_incompatible"
        if not self._lane_fits(robot, cap, task.end_lane):
            return False, "end_lane_incompatible"
        return True, ""

    def _lane_fits(self, robot: FleetState, cap: CapabilityVector, lane_id: str) -> bool:
        lane = self._lane(lane_id)
        if lane is None:
            return True  # no lane data → assume compatible (lenient default)
        models = cap.supported_models or [model_of(robot)]
        if not lane.allows_any(models):
            return False
        if not cap.can_traverse(lane.env):
            return False
        return True

    def utility(self, robot: FleetState, task: Task) -> float:
        """Function Spec §5.1 calculate_utility (post-filter)."""
        distance = max(self._distance(robot.pose.last_node_id, task.start_lane), 0.0)
        distance_score = 1.0 / (1.0 + distance)  # normalized so distance and reputation are comparable
        reputation_score = self.reputation.score(robot.robot_id)
        # RaaS cost term: γ > 0 and economic model registered → subtract cost.
        cost_score = 0.0
        if self.economic is not None and self.cfg.cost_weight > 0.0:
            cost_score = self.economic.marginal_cost_per_km(robot.robot_id)

        alpha = 1.0  # distance_weight
        beta = 1.0   # reputation_weight
        gamma = self.cfg.cost_weight  # 默认 0

        # Higher cost lowers utility; γ controls strength.
        u = alpha * distance_score + beta * reputation_score - gamma * cost_score
        # 优先级加权: urgent 任务对同一机器人的效用放大.
        u *= (1.0 + 0.5 * task.priority)
        return u

    def allocate(self, task: Task, candidates: list[FleetState]) -> AllocationResult:
        """Pick the highest-utility IDLE, capable, non-degraded robot for ``task``."""
        # 1) IDLE + non-degraded (v4.0 §5.2: 降级机器人不再接受新任务)
        idle = [r for r in candidates if r.mode is RobotMode.IDLE and not r.degraded]
        if not idle:
            return AllocationResult(False, task.task_id, reason="no_idle_robot")

        # 2) v4.0 补丁3: capability + env + action-primitive filter
        capable = []
        for r in idle:
            ok, reason = self.can_execute(r, task)
            if ok:
                capable.append(r)
            # reason discarded here; aggregated rejection stats belong to telemetry
        if not capable:
            return AllocationResult(False, task.task_id, reason="no_capable_robot")

        # 3) utility-rank the survivors
        best = max(capable, key=lambda r: self.utility(r, task))
        u = self.utility(best, task)
        return AllocationResult(
            assigned=True,
            task_id=task.task_id,
            robot_id=best.robot_id,
            utility=u,
        )

    def assign_path(self, task: Task, max_speed: float = 1.5) -> TaskAssignment:
        """Build the downlink TaskAssignment for an already-decided allocation."""
        if self._path_finder is not None:
            path = self._path_finder(task.start_lane, task.end_lane)
            if path:
                return TaskAssignment(
                    task_id=task.task_id,
                    path=path,
                    max_speed=max_speed,
                )
        return TaskAssignment(
            task_id=task.task_id,
            path=[task.start_lane, task.end_lane],
            max_speed=max_speed,
        )


def model_of(robot: FleetState) -> str:
    """Derive a model tag for lane allowed_models matching.

    Real deployments carry the model on the robot registry; until then we
    use the robot_id prefix (e.g. 'MIR_001' → 'MIR') as a coarse proxy.
    """
    return robot.robot_id.split("_", 1)[0] if "_" in robot.robot_id else robot.robot_id


__all__ = ["AllocationResult", "Task", "TaskAllocator"]
# keep CapabilityVector import live for type-checkers / re-export convenience
_ = CapabilityVector  # noqa: F841
