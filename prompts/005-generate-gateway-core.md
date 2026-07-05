---
prompt_id: 005
title: 生成消息网关核心代码
model_tested: Claude 3.5 Sonnet
date: 2026-07-15
input: {fastapi_version, kafka_topic, es_index, platform_configs}
output: {gateway_app, adapters, validator, audit_logger}
known_limitations: "Kafka consumer 需要异步初始化，启动顺序敏感"
---

# Prompt: 生成消息网关核心代码

## 上下文
你是一个 SAP-EWM 机器人调度平台的消息网关开发者。需要生成 FastAPI 消息网关的核心代码。

## 技术栈约束
- Python 3.11+
- FastAPI + uvicorn
- aiokafka (Kafka consumer)
- elasticsearch-async (audit log)
- redis (state cache, anti-replay)

## 输入
- 平台配置: 企业微信/飞书/钉钉/SMTP 的 API 凭证
- Kafka topic: `platform_alerts` (消费) / `gateway_callbacks` (生产)
- ES index: `gateway_audit-logs`
- Redis DB: 2 (网关专用)

## 输出要求
1. `main.py` - FastAPI 应用入口，包含所有 API 端点
2. `action_validator.py` - 六重校验（身份/权限/对象/防重放/二次确认/执行前）
3. `message_router.py` - 多渠道路由、优先级、去重、时段控制
4. `card_template_engine.py` - 三平台卡片模板生成
5. `audit_logger.py` - Elasticsearch 审计日志
6. `email_gateway.py` - SMTP 邮件发送
7. 平台适配器: `wechat.py` / `feishu.py` / `dingtalk.py`

## 铁律
- 所有写操作必须通过结构化按钮触发，禁止 NLU 直接执行
- 平台回调必须验证签名
- 审计日志不可篡改，保留 ≥3 年
- 危险操作需要二次确认
- 消息网关独立部署，通过 Kafka 与核心业务主板解耦

## 接口定义
- `POST /api/v1/notifications/send` - 系统发送通知
- `POST /webhook/{platform}` - 平台统一回调
- `GET /api/v1/operations/{id}` - 查询操作状态
- `GET /api/v1/audit/logs` - 查询审计日志
