# 异构机器人融合平台 v5.1 — Core Platform

Initial architecture modules for the v5.x design (`Reference/Design - Core/异构机器人融合平台_v5.0_完整堡垒版.md`).
This package is the Open-RMF-style scheduling / governance / survival core that
sits **above** the existing v4.1 VDA5050 fabric (MQTT / Node-RED / sap-bridge).
The two coexist via the `version_router` (N-1 兼容) — no flag-day cutover.

## Layer → module map（白皮书 §1 / 完整堡垒版 §1.1）

| Whitepaper layer | Module | Core function | Status |
|---|---|---|---|
| 基础设施层 | — | PTP / DDS Discovery / etcd / WORM storage | PLANNED |
| 治理层 | `governance/reputation_engine.py` | 贪心 + 信誉度加权效用 (陷阱 #1) | IMPLEMENTED |
| 治理层 | `governance/economic_model.py` | RaaS γ=0 预留 (灰犀牛 #14) | IMPLEMENTED |
| 应用层 | — | Web Dashboard / API / Playback | PLANNED |
| 核心调度层 | `scheduling/task_allocator.py` | 贪心 + 信誉度加权效用 (陷阱 #1) | IMPLEMENTED |
| 核心调度层 | `scheduling/traffic_light_controller.py` | GREEN→YELLOW→RED FSM + 紧急切灯 (§2.2) | IMPLEMENTED |
| 核心调度层 | `scheduling/facility_manager.py` | Zone Lockdown + 30s 僵尸清理 (陷阱 #2) | IMPLEMENTED |
| 平台服务层 | `platform/fixed_lane_map.py` | 图层化地图 物理层+语义覆盖层 (陷阱 #6) | IMPLEMENTED |
| 平台服务层 | `platform/robot_as_obstacle.py` | 安全气泡 + 1.5m 虚拟墙 (灰犀牛 #4) | IMPLEMENTED |
| 平台服务层 | `platform/failover_degrade.py` | 心跳→DEGRADED 0.3m/s→OFFLINE (§2.2) | IMPLEMENTED |
| 平台服务层 | `platform/charger_reservation.py` | ≤20% 强制锁桩 (陷阱 #7) | IMPLEMENTED |
| 平台服务层 | `platform/lift_manager.py` | 单占用电梯预约 + 超时释放 | IMPLEMENTED |
| 适配层 | `adapter/fleet_adapter.py` | SDK 框架 + 心跳 + boot_id 接管 (附录A.5) | IMPLEMENTED |
| 适配层 | `adapter/shadow_state_machine.py` | 影子状态机 + 超时熔断 + 硬编码后退 | IMPLEMENTED |
| 安全 | `safety/safe_distance.py` | S=V·K+RTT·V+C, 1.5m 法律硬下限 (§2.3) | IMPLEMENTED |
| 生存层 | `survival/worm_blackbox.py` | 哈希链 WORM, 24h滚动, 因果回放 (陷阱 #12) | IMPLEMENTED |
| 生存层 | `survival/version_router.py` | v5.0↔v4.x N-1 兼容 (灰犀牛 #7) | IMPLEMENTED |
| 接口 | `messages/types.py` | FleetState / TaskAssignment / TrafficLightState (§1) | IMPLEMENTED |

## The three iron laws（白皮书 §4 / 完整堡垒版 §2.4）

1. **治理层 — 零信任博弈**: every cross-boundary datum is dirty by default,
   every participant an opportunist. → `governance/`
2. **物理层 — 熵增冗余**: logic optimises, physics pays for the worst case.
   Hard floor 1.5 m is non-overridable. → `safety/`
3. **生存层 — 因果存证**: full causal chain reconstructable in 5 min.
   → `survival/worm_blackbox.py`

## 18 灰犀牛防御矩阵（完整堡垒版 §3）

| # | 类别 | 陷阱 | 补丁位置 |
|---|------|------|----------|
| 1 | 逻辑 | 任务分配缺位 | `scheduling/task_allocator.py` |
| 2 | 逻辑 | 僵尸占位 | `scheduling/facility_manager.py` |
| 3 | 逻辑 | 冷启动流量冲击 | 启动脚本 / 注册错峰 |
| 4 | 逻辑 | 级联延迟放大 | `task_allocator.py` 滚动时域 |
| 5 | 逻辑 | 并发写冲突 | etcd（PLANNED） |
| 6 | 逻辑 | 饥饿死锁 | `task_allocator.py` |
| 7 | 逻辑 | 版本泥潭 | `survival/version_router.py` |
| 8 | 运维 | 人工介入风险 | `scheduling/facility_manager.py` |
| 9 | 运维 | Adapter 僵尸 | `adapter/shadow_state_machine.py` |
| 10 | 运维 | WORM 衰减 | `survival/worm_blackbox.py` |
| 11 | 运维 | 知识断层 | `config.py` + 文档 |
| 12 | 运维 | 验收陷阱 | Ground Truth 流程 |
| 13 | 物理 | 坐标漂移 | `safety/safe_distance.py` |
| 14 | 物理 | 金属反射 | 采购规范 |
| 15 | 物理 | 光照退化 | 采购规范 |
| 16 | 物理 | 地面摩擦系数 | 验收规范 |
| 17 | 安全 | DDS 加密 | 基础设施（PLANNED） |
| 18 | 安全 | 身份漂移 | `adapter/fleet_adapter.py` / `failover_degrade.py` |

## Run

```bash
# from repo root
python -m pytest core/tests/ -q
ruff check core/
```

## Status

Skeleton + core logic for every whitepaper core function. Transport (DDS),
the platform tick loop, and the Web Dashboard wiring are intentionally **not**
in this layer — they are the next milestone (阶段一 生存期 Exit Criteria).
See `traffic_coordinator_v5/10_adr/` for the full set of v5.0 ADRs and `traffic_coordinator_v5/01_architecture/`
for the architecture overview.

---

*文档版本：v5.1 | 最后更新：2026-07-09 | 权威来源：Design Core 完整堡垒版*
