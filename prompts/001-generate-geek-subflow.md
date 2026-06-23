---
prompt_id: 001
title: 生成极智嘉机器人 Sub-flow
model_tested: Kimi K2.6, Claude Sonnet 4.6
date: 2026-06-01
version: 1.0
input: {api_doc, brand_name, protocol_type}
output: {subflow_json, node_config, error_handling}
known_limitations: "MQTT QoS 2 支持需手动验证；极智嘉 RS8 区域锁 API 版本不统一需人工适配"
---

# Prompt: 生成极智嘉机器人 Sub-flow

## 输入
- 机器人型号：GEEK+ M100 / P800 / RS8
- 任务类型：搬运 / 拣选 / 盘点
- 目标库位：A01-02-03

## 输出
- Node-RED Sub-flow JSON（仅 Function 节点 JS 代码）
- 必须包含：急停检查、电量检查、区域锁检查
- 禁止输出完整的 flows.json

## 限制
- 仅使用 JavaScript (ES6+)
- 必须调用 safeLoop/safeExec
- 必须处理 api_deviation_log 记录
