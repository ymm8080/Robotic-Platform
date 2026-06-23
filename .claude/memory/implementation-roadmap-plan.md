---
name: implementation-roadmap
description: 平台版本规划、多仓库部署架构、升级路径
metadata: 
  node_type: memory
  type: reference
  tags: 
    - roadmap
    - architecture
    - planning
  originSessionId: 27d4ae34-931c-483c-9433-c808986b12d8
---

# 实施路线图参考

## 当前版本栈 (v3.4)
- Node-RED 3.1.9
- Python 3.11
- Redis 7
- SQLite（v3.x 存储）
- Mosquitto MQTT

## 多仓库部署
- 每个仓库独立 `.env` + `docker-compose.yml`
- 资源隔离：Redis DB 编号、MQTT topic 前缀 `WAREHOUSE_ID/`
- 仓库 ID 全局唯一，所有消息/日志带 `warehouse_id` 标签

## 规划升级路径
| 版本 | 变更 | 备注 |
|------|------|------|
| v4.0 | SQLite → PostgreSQL | outbox 表迁移、状态表迁移 |
| v4.1 | 多品牌策略引擎 | 策略模式 TS 实现 |
| v5.0 | Kubernetes 容器编排 | 水平扩展、滚动更新 |

**Why:** 平台架构演进方向，影响所有技术决策
**How to apply:** 做设计决策时参考此路线图，确保与长期方向一致
