---
prompt_id: 007
title: 生成飞书卡片模板
model_tested: Claude 3.5 Sonnet
date: 2026-07-15
input: {alert_data, action_type, target_info}
output: {feishu_card_json}
known_limitations: "飞书卡片按钮 value 字段有大小限制"
---

# Prompt: 生成飞书卡片模板

## 上下文
为 SAP-EWM 机器人调度平台生成飞书交互式卡片，用于告警通知和操作确认。

## 飞书卡片规范
- msg_type: `interactive`
- card.config.wide_screen_mode: true
- header.template: red(危险) / orange(警告) / blue(信息)
- elements: div(文本) + hr(分割线) + action(按钮组)
- button.type: danger(危险) / primary(主要) / default(默认)

## 按钮规则
- 按钮文案必须包含操作对象（如"确认取消订单 12345"）
- 危险操作使用 danger 类型按钮
- button.value 包含 action_type, target_id, target_type, confirm_required, correlation_id, alert_id
- 二次确认卡片需包含"确认执行"和"取消"两个按钮

## 输入示例
```json
{
  "alert_id": "ALT_20260705_002",
  "priority": "P1",
  "title": "订单取消确认",
  "content": "客户要求取消订单 12345",
  "action_type": "order_cancel",
  "target": {"target_type": "order", "target_id": "12345"},
  "require_confirm": true
}
```

## 输出要求
生成完整的飞书 interactive card JSON payload。
