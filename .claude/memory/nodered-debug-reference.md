---
name: nodered-debug-reference
description: Node-RED 常见错误模式、根因与修复速查表
metadata: 
  node_type: memory
  type: reference
  tags: 
    - nodered
    - debug
    - troubleshooting
  originSessionId: 27d4ae34-931c-483c-9433-c808986b12d8
---

# Node-RED 调试参考

## 常见错误快速定位

| 错误现象 | 根因 | 修复 |
|----------|------|------|
| `[object Object]` 输出 | 忘记 JSON.stringify()，对象直接拼接字符串 | 用 `JSON.stringify(msg)` 输出 |
| `TypeError: Cannot read properties of undefined` | payload 或嵌套字段不存在 | 加精确判空（`!== undefined && !== null`） |
| WAL 文件过大 (>100MB) | 长时间未 checkpoint | 执行 `PRAGMA wal_checkpoint(TRUNCATE)` |
| HTTP 请求超时 | timeout < 10000ms 或下游响应慢 | 设 timeout=10000ms，超时后重试 |
| `msg.payload` 被 undefined 覆盖 | `msg.payload = {}` 后丢失原数据 | 用 `Object.assign({}, msg.payload, newData)` |
| 流部署后状态消失 | `context` 存了非序列化对象 | 只存 JSON-serializable 值 |
| 飞书通知重复 | 重试机制导致重复投递 | 加幂等键检查 |

## 调试配置
- 生产环境 `debugMaxLength=1000`（禁止展开全部 payload）
- 禁用全局 debug 节点（使用 CATCH_GLOBAL 替代）
- 调试日志通过 `audit_log` 表查询，不依赖 Node-RED 侧边栏

**Why:** Node-RED 调试日志难读，常见错误反复出现
**How to apply:** 遇到异常输出时先查此表
**Related:** [[010-nodered-core]]
