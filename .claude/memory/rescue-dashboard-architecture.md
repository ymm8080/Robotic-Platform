---
name: rescue-dashboard-architecture
description: Rescue Dashboard 离线容灾架构，E-Stop/Safe Mode 设计
metadata: 
  node_type: memory
  type: reference
  tags: 
    - rescue
    - dashboard
    - architecture
    - offline
  originSessionId: 27d4ae34-931c-483c-9433-c808986b12d8
---

# Rescue Dashboard 架构参考

## 设计原则
- 独立 Nginx 容器（端口 8080），不依赖 Node-RED / SAP Bridge
- 纯静态 HTML/JS（无后端运行时依赖）
- 通过 `/api/system-health` 轮询各服务健康状态
- Service Worker 离线缓存确保 Node-RED 挂掉时面板仍可用

## 安全模式触发条件
- Redis OOM（内存 > 256MB）
- Node-RED 连续 3 次 health check 失败
- NTP 时钟偏移 > 5 秒
- Checkpoint 卡死超过 30 秒

## 恢复动作
1. 先恢复 Redis（`FLUSHALL` 如果 >90%）
2. 再重启 Node-RED
3. 确认 3 次正常检测后解除安全模式

## E-Stop 设计
- 物理 E-Stop → MQTT LWT → 所有机器人急停
- Dashboard 上有软件 E-Stop 按钮（调用 /api/estop）
- E-Stop 后所有移动指令被 watchdog 拦截

**Why:** Rescue Dashboard 是生产环境最后一道防线
**How to apply:** 修改 rescue dashboard 时参考此架构约束
