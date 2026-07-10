# SAP-EWM 机器人调度平台

> **工业级容错 + 物理级防呆 + 人性化降级**

## v5.0 异构融合 (开发中)

v5.0 基于 Open-RMF 架构重构，将多品牌 VDA5050/MQTT 机器人统一到一个协调器：

| 模块 | 说明 |
|------|------|
| `core/` | RCS 核心（FixedLaneMap、FleetAdapter、Safety、Scheduling、Survival） |
| `traffic_coordinator_v5/` | 交通协调器（地图加载、品牌适配器引导、YAML 设施地图） |
| `sap-bridge/` | SAP EWM ↔ 机器人桥接（品牌策略、MQTT 发布、VDA5050 协议） |
| `dashboard/` | React/TypeScript 控制面板（机器人列表、交通灯、区域锁定、告警） |
| `gateway/` | Node-RED 网关（审计日志、健康检查） |

**当前开发分支**: `DS-V4-Pro`
**修复日志**: [`D:/EWM ROBOT/fixing codes/fixed-log.md`](../fixing codes/fixed-log.md)

### 已完成的阶段性工作

| 阶段 | 状态 | 内容 |
|------|------|------|
| Phase 0 | ✅ | 构建/测试/打包修复（8 项） |
| Phase 1 | ✅ | v5.0 协调器可导入、可配置（YAML 地图、引导程序） |
| Phase 2 | ✅ | VDA5050/MQTT 对接 v5.0 协调器（6 品牌适配器、REST API） |
| Phase 3 | ✅ | Dashboard v5.0 扩展（平台状态 Hook、交通灯面板、区域锁定面板） |
| Phase 4 | ✅ | 文档（修复日志、README 更新） |

## 快速启动

```bash
# 1. 准备环境
cp .env.example .env
vim .env  # 填入真实值

echo "your-sap-password" > secrets/sap_password.txt
chmod 600 secrets/sap_password.txt

# 2. 启动全栈
docker compose up -d --build

# 3. 验证
 curl http://localhost:1880/api/system-health
```

## 文档

- [部署指南](docs/DEPLOY_GUIDE_v3.4.md)
- [48小时检查清单](docs/48h-checklist-v3.4.md)（39项）
- [架构清单](docs/CURSOR_ARCHITECTURE_MANIFEST_v3.4.md)
- [NTP时钟同步](docs/APPENDIX_NTP.md)
- [告警通道降级](docs/APPENDIX_NOTIFICATION.md)
- [灾难恢复演练](docs/APPENDIX_BACKUP.md)

## 版本

- v3.4 FINAL — 2026-06-02（稳定版，生产环境）
- v5.0 开发中 — 2026-07（异构融合架构，分支 `DS-V4-Pro`）
