---
name: rescue-dashboard
description: Rescue dashboard and degradation SOP — Nginx fallback, safe mode triggers (Redis OOM, Node-RED unhealthy, NTP drift), recovery procedures
---

# 急救大屏与降级 SOP

## 架构
- Nginx 独立容器（端口 8080），Node-RED 崩溃时仍可用
- 静态 HTML 轮询 `http://nodered:1880/api/system-health`
- IP 白名单：仅 `RESCUE_DASHBOARD_ALLOWED_IPS` 中的地址可访问

## 安全模式触发条件
- Redis OOM（used_memory > 95% maxmemory）
- Node-RED 连续 3 次不健康
- NTP 时钟漂移 > 30s
- Checkpoint 卡死 > 10000ms

## 恢复流程
1. `docker restart robot-platform-redis`（如果 Redis OOM）
2. `curl -X POST http://localhost:1880/api/restore-mode`
3. 确认机器人全部 ONLINE
4. 通知仓库主管签字确认
