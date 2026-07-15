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

    holder: str | None = None  # res -> 持有它的 robot
    waiters: set[str] = field(default_factory=set)  # res -> 等待该 res 的 robots


class DeadlockPreventer:
    """通道段单实例资源的死锁预防器.

    模型: 一个 robot 同一时刻最多持有多条通道段, 但最多只 *等待* 一条
    (顺序穿越通道段 — 持有当前段, 申请下一段). 等待图边 ``a -> b`` 表示
    ``a`` 正在等待 ``b`` 持有的资源. 环 ⟺ 死锁.
    """

    def __init__(self) -> None:
        self._holders: dict[str, str] = {}  # res -> robot
        self._holds: dict[str, set[str]] = {}  # robot -> {res}
        self._waiting: dict[str, str] = {}  # robot -> res (其唯一待申请 res)
        self._alloc: dict[str, _Allocation] = {}

    # ── 注册 / 内省 ───────────────────────────────────────────
    def _register(self, resource_id: str) -> _Allocation:
        """确保资源有 _Allocation 条目 (内部副作用方法)."""
        return self._alloc.setdefault(resource_id, _Allocation())

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
        a = self._register(resource_id)
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
                # 资源释放后清除残留等待者, 保持 _alloc 与 _waiting 一致
                for waiter in a.waiters.copy():
                    if self._waiting.get(waiter) == resource_id:
                        self._waiting.pop(waiter, None)
                a.waiters.clear()

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
        a = self._register(resource_id)
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

    def _inject_wait_cycle(self, n: int, prefix: str = "R", res_prefix: str = "S") -> None:
        """测试/自检专用: 白盒注入 n 车死锁环 (绕过 may_wait 预防).

        模拟预防被绕过后已形成的环 — 用于 detect_deadlock_ring / break_deadlock 测试.
        正常业务路径不应调用此方法.
        """
        for i in range(n):
            ri, si = f"{prefix}{i}", f"{res_prefix}{i}"
            self._holders[si] = ri
            self._holds.setdefault(ri, set()).add(si)
            self._waiting[ri] = f"{res_prefix}{(i + 1) % n}"
            self._register(si).holder = ri
            self._register(f"{res_prefix}{(i + 1) % n}").waiters.add(ri)

    # ── 环检测 ─────────────────────────────────────────────────
    def _has_cycle(self, start: str, wait_for: dict[str, str]) -> bool:
        """从 *start* 起沿等待图做 DFS, 回边 (灰) = 环.

        等待图下一跳 = node 等待的 res 的当前持有者.
        """
        color: dict[str, int] = {}

        def dfs(u: str) -> bool:
            color[u] = _GRAY
            res = wait_for.get(u)
            nxt = self._holders.get(res) if res is not None else None
            if nxt is not None:
                if color.get(nxt, _WHITE) == _GRAY:
                    return True  # 回边 = 环
                if color.get(nxt, _WHITE) == _WHITE and dfs(nxt):
                    return True
            color[u] = _BLACK
            return False

        return dfs(start)

    # ── 检测解除 (task 4, 灰犀牛 #19 双保险) ───────────────────
    def detect_deadlock_ring(self) -> list[str] | None:
        """检测当前等待图 *已形成* 的死锁环 (reactive 检测).

        与 :meth:`may_wait` 的 *预防* 正交: 预防拒绝成环的新等待; 本方法处理
        *已形成* 的环 (预防被绕过 / 外部状态变更 / legacy 路径). 返回环中
        robot 列表 (任一环), 无环返回 None.

        等待图是 functional graph (每 robot 最多一条等待边, out-degree ≤ 1),
        故环检测 = 顺链走, 回到链中节点即环.
        """
        for start in self._waiting:
            ring = self._find_cycle_path(start)
            if ring:
                return ring
        return None

    def _find_cycle_path(self, start: str) -> list[str] | None:
        """从 start 顺等待链走, 返回环节点列表或 None (无环 / 链终止)."""
        chain: list[str] = []
        pos: dict[str, int] = {}
        cur: str | None = start
        while cur is not None and cur not in pos:
            pos[cur] = len(chain)
            chain.append(cur)
            res = self._waiting.get(cur)
            cur = self._holders.get(res) if res is not None else None
        if cur is None:
            return None  # 链终止, 无环
        return chain[pos[cur] :]  # cur 在链中 → 从其位置起为环

    def break_deadlock(self, ring: list[str], priority_by_robot: dict[str, int]) -> str:
        """死锁解除: 强制最低优先级车退避让点 (task 4, v5.x 检测解除).

        Args:
            ring: detect_deadlock_ring 返回的死锁环节点列表.
            priority_by_robot: robot -> 优先级值映射.

        Convention:
            **数值小 = 低优先级 = 退避** (同 traffic_light_controller v5.x).
            调用方负责把自身优先级体系映射到此.
            未登记的 robot 默认 0 (最低优先级 → 退避).

        Returns:
            应退避让点的 robot_id (环中优先级值最小的 robot).
        多个 robot 优先级相同时, 返回环中遍历顺序靠前的 (确定性选择).
        """
        return min(ring, key=lambda r: priority_by_robot.get(r, 0))


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

    # task 4: 检测解除 — 预防被绕过后已形成的 3 车环
    p2 = DeadlockPreventer()
    p2._inject_wait_cycle(3)  # 白盒注入 3 车环 (模拟预防被绕过)
    ring = p2.detect_deadlock_ring()
    assert ring is not None and set(ring) == {"R0", "R1", "R2"}, f"ring={ring}"
    # R1 优先级最低 (值最小) → 退避让点
    yielder = p2.break_deadlock(ring, {"R0": 5, "R1": 1, "R2": 3})
    assert yielder == "R1", f"yielder={yielder}"
    print("OK: 4-vehicle ring — deadlock entry rejected, 0 deadlock")


if __name__ == "__main__":
    _demo()
