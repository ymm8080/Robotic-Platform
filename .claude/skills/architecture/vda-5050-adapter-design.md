---
name: vda-5050-adapter-design
description: VDA5050 multi-brand robot adapter design — strategy pattern, MQTT topics, heartbeat, battery management
---

# VDA5050 适配器设计

## 架构
- 品牌适配采用策略模式：`adapter = get_adapter(brand)` 
- 每个品牌实现 `navigate()`, `pick()`, `place()`, `status()` 接口
- 统一入参：`{order_id, location, zone_token, priority}`

## MQTT 主题
- `vda5050/{manufacturer}/{serialNumber}/connection` — 连接状态
- `vda5050/{manufacturer}/{serialNumber}/state` — 状态报告
- `vda5050/{manufacturer}/{serialNumber}/order` — 订单下发

## 心跳检测
- 120s 无心跳 → OFFLINE（不是 90s，防止 WiFi 漫游误判）
- 恢复心跳后 10s 内自动恢复 ONLINE

## 电量管理
- < 20% 限制短单（≤ 50 米）
- < 10% 强制回充
