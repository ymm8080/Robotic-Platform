---
prompt_id: 006
title: 生成企业微信卡片模板
model_tested: Claude 3.5 Sonnet
date: 2026-07-15
input: {alert_data, action_type, target_info}
output: {wechat_card_json}
known_limitations: "企业微信模板卡片按钮需后续消息发送"
---

# Prompt: 生成企业微信卡片模板

## 上下文
为 SAP-EWM 机器人调度平台生成企业微信模板卡片，用于告警通知和操作确认。

## 企业微信模板卡片规范
- msgtype: `template_card`
- card_type: `text_notice` (文本通知型)
- source.desc: 来源描述
- main_title: 标题+描述
- emphasis_content: 强调内容（目标ID）
- card_action: 卡片整体点击行为

## 按钮规则
- 按钮文案必须包含操作对象（如"确认急停 R-01"）
- 危险操作按钮使用 danger 样式
- 按钮通过后续消息发送（模板卡片本身不支持内嵌按钮）

## 输入示例
```json
{
  "alert_id": "ALT_20260705_001",
  "priority": "P0",
  "title": "机器人路径冲突告警",
  "content": "机器人 R-01 在 Zone-A 与 R-02 路径冲突",
  "action_type": "robot_stop",
  "target": {"target_type": "robot", "target_id": "R-01"}
}
```

## 输出要求
生成完整的企业微信 template_card JSON payload，包含按钮动作数据。
