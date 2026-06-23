---
name: robot-firmware-ota
description: Robot firmware OTA risk management — API baseline recording, automated regression testing, deviation detection, brand suspension
---

# 机器人固件 OTA 管控

## 风险
OTA 后厂商 API 行为可能变更（新增字段、修改响应格式）

## 管控流程
1. OTA 前在 `api_deviation_log` 记录当前 API 版本基线
2. OTA 后自动执行回归测试（Mock + 真机）
3. API 偏差检测：`expected_position != actual_position` → 记录证据
4. 偏差 >3 次 → 自动挂起该品牌所有新订单

## 降级
- OTA 期间使用备机（同品牌不同固件版本）
- 紧急回滚：联系厂商降级固件
