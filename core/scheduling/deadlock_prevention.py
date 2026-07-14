"""通道段资源分配前死锁预防 (v7 Phase 4, 灰犀牛 #19).

与 ``traffic_light_controller.detect_deadlocks`` 的 *检测解除* (死锁已形成后
强制低优先级车后退 5m) 正交: 本模块是 *预防* — 在机器人进入通道段资源前模拟
分配后状态, 若进入死锁区则拒绝, 车区外等待.

v7 架构说明书要求 "Petri 网状态方程显示进死锁区则拒绝". 在本平台的资源模型下
(每条通道段同一时刻仅一车持有 = 单实例可复用资源), Petri 网死锁可达性条件
退化为 **资源分配图 (RAG) 环检测**: 单实例资源下, 等待图出现环 ⟺ 死锁.
故用 O(V+E) DFS 环检测等价实现, 无需显式 Petri 网建模.

# ponytail: 单实例资源下 Petri 状态方程 = RAG 环检测. 升级路径: 当通道段允许多车
# (多实例资源) 时改用 Banker 算法或显式 Petri 不变量 (T-不变量) 检测.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# DFS 着色: 未访问 / 在栈中 (灰) / 已完成 (黑). 回边 (灰) = 环.
_WHITE, _GRAY, _BLACK = 0, 1, 2


@dataclass
class _Allocation:
    """通道段分配快照 (用于 introspection / 测试)."""

    holder: str | None = None                       # res -> 持有它的 robot
    waiters: set[str] = field(default_factory=set)  # res -> 等待该 res 的 robots


class DeadlockPreventer:
    """通道段单实例资源的死锁预防器.

    模型: 一个 robot 同一时刻最多持有多条通道段, 但最多只 *等待* 一条
    (顺序穿越通道段 — 持有当前段, 申请下一段). 等待图边 ``a -> b`` 表示
    ``a`` 正在等待 ``b`` 持有的资源. 环 ⟺ 死锁.
    """

    def __init__(self) -> None:
        self._holders: dict[str, str] = {}        # res -> robot
        self._holds: dict[str, set[str]] = {}     # robot -> {res}
        self._waiting: dict[str, str] = {}        # robot -> res (其唯一待申请 res)
        self._alloc: dict[str, _Allocation] = {}

    # ── 注册 / 内省 ───────────────────────────────────────────
    def register(self, resource_id: str) -> _Allocation:
        a = self._alloc.setdefault(resource_id, _Allocation())
        return a

    def held_by(self, resource_id: str) -> str | None:
        return self._holders.get(resource_id)

    def holds(self, robot_id: str) -> set[str]:
        return set(self._holds.get(robot_id, ()))

    def waiting_for(self, robot_id: str) -> str | None:
        return self._waiting.get(robot_id)

    # ── 持有 / 释放 ───────────────────────────────────────────
    def acquire(self, robot_id: str, resource_id: str) -> bool:
        """资源空闲则授予 (单实例空闲资源永不引发死锁). 占用中返回 False.

        调用方在 False 时应改用 :meth:`may_wait` 决定等待还是改道.
        """
        if self._holders.get(resource_id) is not None:
            return False
        self._holders[resource_id] = robot_id
        self._holds.setdefault(robot_id, set()).add(resource_id)
        a = self.register(resource_id)
        a.holder = robot_id
        # 若此前该 robot 在等此 res, 等待已满足
        if self._waiting.get(robot_id) == resource_id:
            self._clear_wait(robot_id)
        return True

    def release(self, robot_id: str, resource_id: str) -> None:
        if self._holders.get(resource_id) == robot_id:
            self._holders.pop(resource_id, None)
            held = self._holds.get(robot_id)
            if held is not None:
                held.discard(resource_id)
                if not held:
                    self._holds.pop(robot_id, None)
            a = self._alloc.get(resource_id)
            if a is not None:
                a.holder = None

    # ── 预防核心 ───────────────────────────────────────────────
    def would_deadlock(self, robot_id: str, resource_id: str) -> bool:
        """模拟 robot 等待 resource 后是否成环 (进死锁区).

        资源空闲或已被自己持有时永不成环. 仅当等待他车持有的资源时,
        加入临时等待边并从 robot 起做环检测.
        """
        holder = self._holders.get(resource_id)
        if holder is None or holder == robot_id:
            return False
        # 临时等待图: robot -> holder(res) 的持有者链
        wait_for: dict[str, str] = dict(self._waiting)
        wait_for[robot_id] = resource_id
        return self._has_cycle(robot_id, wait_for)

    def may_wait(self, robot_id: str, resource_id: str) -> bool:
        """机器人是否可安全等待该资源.

        True: 可在区外等待 (等待边已登记, 后续 transitive 环会被捕捉).
        False: 等待将成环 → 拒绝, 调用方须改道 / 让点.
        """
        holder = self._holders.get(resource_id)
        if holder is None or holder == robot_id:
            return True  # 无需等待
        if self.would_deadlock(robot_id, resource_id):
            return False
        self._waiting[robot_id] = resource_id
        a = self.register(resource_id)
        a.waiters.add(robot_id)
        return True

    def _clear_wait(self, robot_id: str) -> None:
        res = self._waiting.pop(robot_id, None)
        if res is not None:
            a = self._alloc.get(res)
            if a is not None:
                a.waiters.discard(robot_id)

    def clear_wait(self, robot_id: str) -> None:
        """机器人改道 / 离开等待时清除其等待边."""
        self._clear_wait(robot_id)

    # ── 环检测 ─────────────────────────────────────────────────
    @staticmethod
    def _resolve_waiter(node: str, wait_for: dict[str, str], holders: dict[str, str]) -> str | None:
        """node 等待的 res 的当前持有者 = 等待图下一跳."""
        res = wait_for.get(node)
        if res is None:
            return None
        return holders.get(res)

    def _has_cycle(self, start: str, wait_for: dict[str, str]) -> bool:
        color: dict[str, int] = {}

        def dfs(u: str) -> bool:
            color[u] = _GRAY
            nxt = self._resolve_waiter(u, wait_for, self._holders)
            if nxt is not None:
                if color.get(nxt, _WHITE) == _GRAY:
                    return True  # 回边 = 环
                if color.get(nxt, _WHITE) == _WHITE and dfs(nxt):
                    return True
            color[u] = _BLACK
            return False

        return dfs(start)


# ── 自检 (DoD: 4 车环形死锁拓扑拒绝进死锁区, 0 死锁) ─────────────
def _demo() -> None:
    p = DeadlockPreventer()
    # 4 车各占一段
    for i in range(4):
        assert p.acquire(f"R{i}", f"S{i}"), f"R{i} should acquire free S{i}"
    # 顺时针申请下一段 — 前 3 个等待安全, 第 4 个成环被拒
    safe = p.may_wait("R0", "S1")
    assert safe, "R0->S1 safe (R1 not waiting yet)"
    assert p.may_wait("R1", "S2"), "R1->S2 safe"
    assert p.may_wait("R2", "S3"), "R2->S3 safe"
    rejected = not p.may_wait("R3", "S0")
    assert rejected, "R3->S0 must be rejected (closes 4-cycle deadlock)"
    # 释放后环解除, R3 可等待
    p.release("R0", "S0")
    p.clear_wait("R0")
    assert p.held_by("S0") is None, "S0 freed after R0 release"
    print("OK: 4-vehicle ring — deadlock entry rejected, 0 deadlock")


if __name__ == "__main__":
    _demo()
