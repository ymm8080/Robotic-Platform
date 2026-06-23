---
name: node-red-data-boundary
description: Node-RED data boundary and performance circuit breaking — CPU/checkpoint rate limiting, SQLite WAL protection, safe function utilities
---

# Node-RED 数据边界与性能熔断

## 限流阈值
- CPU > 80% + Checkpoint > 5000ms → 限流至 30%（不低于 10 单/秒）
- Checkpoint > 10000ms → 降至 15 单/秒
- 连续 3 次巡检正常 → 自动解除

## SQLite WAL 防护
- WAL > 100MB → 触发限流
- 每月凌晨执行 `PRAGMA wal_checkpoint(TRUNCATE)`
- 高频表禁用 `AUTOINCREMENT`，使用 `INTEGER PRIMARY KEY`（64 位）

## 安全函数
所有 Function 节点引用全局安全函数：
- `safeLoop(arr, cb, node, context)` — 隐式循环阻断
- `safeParse(jsonStr, node)` — JSON 大小限制 50KB
- `safeExec(fn, node, timeoutMs)` — 函数耗时限制
- `redactSensitive(obj)` — 脱敏后输出日志
