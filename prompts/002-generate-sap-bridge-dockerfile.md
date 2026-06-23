---
prompt_id: 002
title: 生成 SAP 桥接层 Dockerfile
model_tested: Claude Sonnet 4.6
date: 2026-06-01
version: 1.0
input: {python_version, dependencies, sap_rfc_library}
output: {dockerfile, docker_compose_snippet}
known_limitations: "pyrfc 版本与 SAP NW RFC SDK 需严格匹配；SAP 连接池大小需根据 SAP 许可证调整"
---

# Prompt: 生成 SAP 桥接层 Dockerfile

## 输入
- Python 版本：3.11
- 依赖：pyrfc, redis, fastapi, uvicorn

## 输出
- Dockerfile（基于 python:3.11-slim）
- docker-compose 服务定义片段

## 限制
- 绝对禁止 Alpine
- 必须包含 healthcheck
- 必须配置非 root 用户
