---
prompt_id: 008
title: 生成钉钉卡片模板
model_tested: Claude 3.5 Sonnet
date: 2026-07-15
input: {alert_data, action_type, target_info}
output: {dingtalk_card_json}
known_limitations: "钉钉 ActionCard 按钮通过 URL 回调，需解析 query params"
---

# Prompt: 生成钉钉卡片模板

## 上下文
为 SAP-EWM 机器人调度平台生成钉钉 ActionCard，用于告警通知和操作确认。

## 钉钉 ActionCard 规范
- msgtype: `action_card`
- action_card.title: 卡片标题
- action_card.markdown: Markdown 格式正文
- action_card.btn_orientation: "0"(竖排) / "1"(横排)
- action_card.btns: 按钮列表 [{title, action_url}]
- action_url: 包含 action, target, type, alert_id, corr 等 query params

## 按钮规则
- 按钮文案必须包含操作对象（如"确认召回 R-03"）
- 回调 URL 格式: `https://ewma.example.com/api/callback?action={action_type}&target={target_id}&type={target_type}&alert_id={alert_id}&corr={correlation_id}`
- 二次确认需在 URL 中加 `&token={confirm_token}`

## 输入示例
```json
{
  "alert_id": "ALT_20260705_003",
  "priority": "P1",
  "title": "机器人召回通知",
  "content": "机器人 R-03 电量低于 20%，需回充电站",
  "action_type": "robot_recall",
  "target": {"target_type": "robot", "target_id": "R-03"}
}
```

## 输出要求
生成完整的钉钉 action_card JSON payload，包含所有按钮的 action_url。
