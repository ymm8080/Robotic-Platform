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
