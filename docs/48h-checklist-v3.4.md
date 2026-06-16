# SAP-EWM 机器人调度平台 终极上线前 48 小时检查清单 v3.4

> **适用范围**：生产环境首次上线 / 大版本升级 / 核心架构变更后的强制验收  
> **执行人员**：运维负责人 + 开发负责人 + 仓库主管（三方在场）  
> **执行时长**：48 小时（建议分 6 个 8 小时轮班，避免疲劳误操作）  
> **版本对齐**：本文档对应 `.cursor/rules/VERSION = v3.4`

---

## 📋 验收总览

| 维度 | 检查项数 | 致命(P0) | 严重(P1) | 一般(P2) | 状态 |
|------|---------|---------|---------|---------|------|
| 宪法级规则 | 6 | 4 | 2 | 0 | ⬜ |
| Node-RED 核心主板 | 8 | 3 | 4 | 1 | ⬜ |
| SAP 桥接层 | 4 | 1 | 2 | 1 | ⬜ |
| 机器人适配层 | 5 | 2 | 2 | 1 | ⬜ |
| 深水区加固 | 5 | 2 | 2 | 1 | ⬜ |
| 物理级防呆 | 4 | 2 | 1 | 1 | ⬜ |
| 合规与审计 | 4 | 2 | 1 | 1 | ⬜ |
| 运维与急救 | 4 | 1 | 2 | 1 | ⬜ |
| **合计** | **36** | **17** | **16** | **3** | ⬜ |

> **通过标准**：P0 项 100% 通过，P1 项 ≥95% 通过（允许最多 1 项有条件通过并记录风险），P2 项 ≥90% 通过。

---

## 🏛️ 维度一：宪法级规则（6 项）

### 1. LLM 调度决策绝对禁令 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `000-global-iron-rules.mdc` 第 1 条 |
| **风险** | AI 做派单决策 → 撞车 / 死锁 / 人员伤亡 |
| **命令/方法** | 构造恶意 Prompt 请求 Dify：`{"action": "dispatch", "robot_id": "R001", "target": "A01-02-03"}` |
| **通过标准** | Node-RED 拦截返回 `400 Bad Request`，响应体含 `"error": "LLM 禁止做调度决策"`，订单不进入状态机，飞书告警 `"AI 越权拦截"` |
| **佐证** | `audit_log` 表记录 `event_type='LLM_BLOCKED'` |

### 2. 物理急停硬接线延迟 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `000-global-iron-rules.mdc` 第 2 条 |
| **风险** | 软件急停延迟 >50ms → 人员伤亡 |
| **命令/方法** | 用示波器测量急停按钮触点 → PLC 输出切断动力回路的完整链路（含继电器响应） |
| **通过标准** | 端到端延迟 ≤ 50ms（建议 ≤ 20ms 留余量），Node-RED / Dify / SAP 桥接层**全程不介入**急停链路 |
| **佐证** | 示波器截图存档，文件名 `emergency_stop_latency_{日期}.png` |

### 3. 位移与急停互锁 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `000-global-iron-rules.mdc` 第 3 条 |
| **风险** | 急停状态下发移动指令 → 机械臂/AGV 失控 |
| **命令/方法** | 1. 触发急停（按急停按钮）<br>2. 通过 SAP 推送一单到 Node-RED<br>3. 观察机器人是否收到移动指令 |
| **通过标准** | 急停=True 时，Node-RED 直接返回 `SUSPENDED`，**绝对禁止**向机器人下发任何 `action` 指令（含后退让路），`trace_log` 记录 `BLOCKED_BY_ESTOP` |
| **佐证** | MQTT 抓包：Topic `robots/command/R001` 在急停期间无任何消息 |

### 4. 数据主权合规（Dify 离线模式） [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `000-global-iron-rules.mdc` 第 4 条 / `compliance-checklist.md` |
| **风险** | 运行时连接 HuggingFace 等境外服务 → 数据出境法务风险 |
| **命令/方法** | `docker exec dify env \| grep HF_HUB_OFFLINE` |
| **通过标准** | 必须显示 `HF_HUB_OFFLINE=1`，Dify 启动日志无 `huggingface.co` 连接超时或下载请求 |
| **佐证** | 截图 Dify 环境变量 + 启动日志前 100 行 |

### 5. 凭证无硬编码扫描 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `000-global-iron-rules.mdc` 第 5 条 |
| **风险** | 密码进 Git → 安全事件 / 等保测评不通过 |
| **命令/方法** | `grep -rE "(password|passwd|secret|token|api_key)\s*=\s*["'][^"']+["']" --include="*.js" --include="*.py" --include="*.json" . \| grep -v "\.env\." \| grep -v "example"` |
| **通过标准** | 无硬编码凭证（排除 `.env.example` 中的占位符如 `YOUR_PASSWORD_HERE`），所有敏感配置来自环境变量或 Docker Secrets |
| **佐证** | 扫描结果输出到 `security_scan_{日期}.txt`，0 行匹配 |

### 6. 时区 UTC 统一 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `000-global-iron-rules.mdc` 第 6 条 |
| **风险** | 跨时区订单时间错乱 → 对账困难 / 审计失败 |
| **命令/方法** | `sqlite3 robot_platform.db "SELECT created_at FROM orders ORDER BY id DESC LIMIT 3;"` |
| **通过标准** | 时间戳格式为 UTC（如 `2026-06-02T01:27:00Z`），非本地时间（如 `2026-06-02 09:27:00+08:00`），状态机流转仅依赖逻辑时钟（递增序号） |
| **佐证** | 数据库查询截图 + 与 `server_time` 字段对比确认无时区偏移 |

---

## 🧠 维度二：Node-RED 核心主板（8 项）

### 7. 全局 Catch 闭环验证 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 1 条 |
| **风险** | 异常数据黑洞 → 订单消失无感知 |
| **命令/方法** | 在任意 Function 节点注入：`throw new Error("INTENTIONAL_TEST_ERROR_" + Date.now())` |
| **通过标准** | 全局 Catch 节点触发，消息进入 `dead_letter_queue` 表，飞书/企微收到告警 `"未处理异常：INTENTIONAL_TEST_ERROR_xxx"`，原始消息不丢失 |
| **佐证** | `dead_letter_queue` 表查询该 `error_id`，`status='UNRESOLVED'` |

### 8. 状态机假完成防护 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 2 条 |
| **风险** | 无业务确认自动转 COMPLETED → 库存账实不符 |
| **命令/方法** | 故意让机器人执行空货架任务（模拟扫码失败），观察状态流转 |
| **通过标准** | 订单必须停在 `DIFF_SUSPENDED`，**禁止**自动转 `COMPLETED`，`outbox_events` 记录 `SUSPENDED_REASON='MISSING_SCAN_CONFIRMATION'` |
| **佐证** | SQLite 查询 `SELECT status FROM orders WHERE id=xxx;` 结果为 `DIFF_SUSPENDED` |

### 9. Outbox 双写一致性 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 3 条 |
| **风险** | 状态变更丢失 → SAP 与 WMS 数据不一致 |
| **命令/方法** | 模拟 SQLite 写入失败：`chmod 000 robot_platform.db`，然后触发一单状态变更 |
| **通过标准** | Node-RED 不返回 200 给上游（SAP 桥接层），订单**不进入**状态机，`outbox_events` 无该订单记录，重试 5 次后进入死信队列 |
| **佐证** | 恢复权限后查询 `outbox_events` 和 `dead_letter_queue`，确认无脏数据 |

### 10. 入库拒收机制（JSON Schema 校验） [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 4 条 |
| **风险** | SAP 垃圾数据进入状态机 → 异常订单污染 |
| **命令/方法** | `curl -X POST http://nodered:1880/api/orders -H "Content-Type: application/json" -d '{"weight":0,"location":null}'` |
| **通过标准** | Node-RED 返回 `400 Bad Request`，响应体含具体错误（如 `"weight must be > 0"`），状态机不流入，SAP 收到明确拒收原因 |
| **佐证** | HTTP 响应截图 + `orders` 表确认无该单记录 |

### 11. 跨品牌区域锁（zone_token） [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 5 条 |
| **风险** | 极智嘉与海康机器人同区域作业 → 死锁 / 碰撞 |
| **命令/方法** | 1. 极智嘉机器人 R001 进入 Zone-A<br>2. 海康机器人 R101 申请进入 Zone-A |
| **通过标准** | R101 的派单请求被挂起（`PENDING_ZONE_LOCK`），`zone_lock` 表记录 `zone_id='Zone-A', robot_id='R001', brand='geekplus', zone_token=uuid`，R101 携带的 `zone_token` 不匹配被拦截 |
| **佐证** | `zone_lock` 表查询 + MQTT Topic `robots/command/R101` 无进入 Zone-A 的指令 |

### 12. 逆向物流 force_sync [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 6 条 |
| **风险** | SAP 盘点/退货时库位锁无法释放 → 冲突订单永久挂起 |
| **命令/方法** | `curl -X POST http://nodered:1880/api/force_sync -d '{"location":"A01-02-03","reason":"INVENTORY_CHECK"}'` |
| **通过标准** | A01-02-03 的 `zone_lock` 被强制清空，该库位所有冲突订单状态变为 `SUSPENDED`（非删除），`outbox_events` 记录 `FORCE_SYNC` 事件 |
| **佐证** | `zone_lock` 表该 location 无记录 + `orders` 表原冲突单状态为 `SUSPENDED` |

### 13. 配置热更新灰度（5 分钟延迟） [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 7 条 |
| **风险** | 规则瞬间全量生效 → 雪崩 |
| **命令/方法** | `UPDATE dispatch_rules SET effective_from = datetime('now', '+5 minutes') WHERE id=999;` |
| **通过标准** | 5 分钟内旧规则生效（新单按旧规则派单），5 分钟后新规则生效，`dispatch_rules` 表 `effective_from` 精确到秒，无瞬间切换 |
| **佐证** | 分别在 T+0、T+3min、T+6min 发单，对比 `orders.assigned_rule_id` 字段 |

### 14. msg 对象防御（falsy 值修正） [P2]

| 属性 | 内容 |
|------|------|
| **来源** | `010-nodered-core.mdc` 第 8 条（v3.4 修正） |
| **风险** | `msg.payload = 0`（重量为0）被误判为 `{}` → 拒收逻辑失效 |
| **命令/方法** | 在 Function 节点注入 `msg.payload = 0`，观察后续流程 |
| **通过标准** | `payload` 保持为 `0`（而非被抹杀为 `{}`），下游 JSON Schema 校验正确捕获 `weight=0` 并拒收 |
| **佐证** | Function 节点 `node.warn(payload)` 输出 `0`，非 `[object Object]` |

---

## 🔌 维度三：SAP 桥接层（4 项）

### 15. 异步队列 202 响应 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `020-sap-bridge.mdc` 第 2 条 |
| **风险** | SAP 同步等待超时 → 触发重发炸弹 |
| **命令/方法** | `curl -w "%{http_code}
%{time_total}" -X POST http://sap-bridge:8000/api/rfc -d '{"function":"Z_EWM_CREATE_TASK","params":{...}}'` |
| **通过标准** | HTTP 状态码 **202**（非 200），响应时间 < 200ms，`time_total` < 0.5s，Redis 队列 `sap:queue` 中有该任务，5 秒内被消费 |
| **佐证** | `redis-cli LRANGE sap:queue 0 -1` 确认任务存在 + SAP SM37 查看后台作业 |

### 16. pyrfc 连接泄漏 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `020-sap-bridge.mdc` 第 3 条 |
| **风险** | SM04 连接数爆炸 → SAP Basis 报警 / 系统锁定 |
| **命令/方法** | `seq 100 \| xargs -P5 -I{} curl -s -o /dev/null -w "%{http_code}
" http://sap-bridge:8000/api/rfc`，同时 SAP 事务码 SM04 观察 |
| **通过标准** | 5 并发持续调用下 SM04 峰值连接数 ≤ 5，**测试结束后 30 秒内 SM04 归零**（无残留连接） |
| **佐证** | SM04 截图（峰值 + 测试结束后）+ `pyrfc` 日志无 `ConnectionPool` 溢出警告 |

### 17. 异常友好化（德语屏蔽） [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `020-sap-bridge.mdc` 第 4 条 |
| **风险** | 原始 SAP 德语异常透传 → 现场人员无法理解 |
| **命令/方法** | 模拟 SAP 异常：修改桥接层临时抛出 `pyrfc._exception.ABAPApplicationError: "Fehler: Material nicht gefunden"` |
| **通过标准** | Dify/前端收到的响应为中文：`"错误：物料未找到，请检查物料编码是否输入正确"`，**不含任何德语原文** |
| **佐证** | 抓包 Dify 收到的 JSON，`error.message` 为纯中文 |

### 18. 镜像安全（禁用 Alpine） [P2]

| 属性 | 内容 |
|------|------|
| **来源** | `020-sap-bridge.mdc` 第 1 条 |
| **风险** | Alpine musl libc 与 pyrfc 兼容性问题 → 随机崩溃 |
| **命令/方法** | `docker inspect sap-bridge \| grep Image` |
| **通过标准** | 镜像必须为 `python:3.11-slim`（或 `python:3.11-bullseye`），**绝对禁止** `alpine` 字样 |
| **佐证** | Dockerfile 首行 `FROM python:3.11-slim` 截图 |

---

## 🤖 维度四：机器人适配层（5 项）

### 19. 电量 <20% 短单限制 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `030-robot-device.mdc` 第 2 条 |
| **风险** | 机器人中途断电 → 货架倾倒 / 通道堵塞 |
| **命令/方法** | 将某机器人电量设为 15%（模拟低电量），触发长距离派单（> 100 米） |
| **通过标准** | 系统**拒绝**派单或自动拆分为短单（每段 ≤ 50 米），飞书/企微提示 `"R001 电量 15%，已限制为短单"` |
| **佐证** | `robot_status` 表 `battery=15`，`orders` 表该机器人任务 `distance ≤ 50` |

### 20. 心跳丢失 120s 判定离线 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `030-robot-device.mdc` 第 2 条 |
| **风险** | WiFi 漫游瞬时丢包 → 误判离线频繁告警 |
| **命令/方法** | 屏蔽某机器人 MQTT 心跳 90 秒，再恢复发送 |
| **通过标准** | 90 秒内无告警，120 秒时才标记 `OFFLINE`，恢复心跳后 10 秒内自动恢复 `ONLINE`，无人工干预 |
| **佐证** | `robot_status` 表 `last_heartbeat` 时间戳 + 飞书告警时间线 |

### 21. 环境染色（env_tag）校验 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `030-robot-device.mdc` 第 3 条 |
| **风险** | 测试车连生产 MQTT → 测试数据污染生产 |
| **命令/方法** | 使用 MQTT 客户端（MQTTX）向 PROD 环境发布：`Topic: robots/heartbeat/R999`, `Payload: {"robot_id":"R999","env_tag":"STAGING","timestamp":"2026-06-02T01:27:00Z"}` |
| **通过标准** | Node-RED **丢弃**该心跳，不更新任何机器人状态，飞书/企微收到告警 `"测试车越界：R999 携带 STAGING 标签连接 PROD 环境"` |
| **佐证** | `robot_status` 表无 R999 记录 + 告警截图 |

### 22. 位移与物理死锁（10 秒卡死检测） [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `030-robot-device.mdc` 第 4 条 / `physical-digital-friction.md` |
| **风险** | 机器人卡死不报异常 → 幽灵堵车 |
| **命令/方法** | 模拟机器人卡死：让真机或 Mock 在 EXECUTING 状态下 10 秒不更新 position |
| **通过标准** | 10 秒无位移变化，系统自动判定 `STUCK`，发后退指令**前**检查急停状态：<br>- 急停=False：下发后退指令，状态转 `RECOVERING`<br>- 急停=True：**禁止**发后退，直接转 `SUSPENDED`，`trace_log` 记录 `STUCK_WITH_ESTOP_ACTIVE` |
| **佐证** | MQTT 抓包 `robots/command/R001`：急停时无后退指令 |

### 23. 厂商 API 偏差日志 [P2]

| 属性 | 内容 |
|------|------|
| **来源** | `030-robot-device.mdc` 第 6 条 |
| **风险** | 厂商 API 行为与文档不符 → 甩锅无证据 |
| **命令/方法** | 模拟厂商 200 OK 但 position 未变化（Mock 返回 `{"code":200,"msg":"success"}` 但机身不动） |
| **通过标准** | `api_deviation_log` 表新增记录：`brand='geekplus'`, `error_type='SILENT_FAILURE'`, `expected_position!=actual_position`，飞书告警 `"厂商 API 静默失败，已记录证据"` |
| **佐证** | `api_deviation_log` 表查询最新 10 条 |

---

## 🌊 维度五：深水区加固（5 项）

### 24. 动态限流（Watchdog 外部触发） [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `node-red-data-boundary.md` 2.1（v3.4 修正） |
| **风险** | 事件循环阻塞时无法自我诊断 → 系统僵死 |
| **命令/方法** | 在 Function 节点故意写 `while(true) {}` 死循环，观察 10 秒内系统反应 |
| **通过标准** | 10 秒内独立 Watchdog 容器触发限流，Redis 写入 `system:throttle_mode=15`（单/秒），Node-RED 收到标志位后派单速率自动下降，**机器人心跳不中断** |
| **佐证** | `docker stats watchdog` 正常 + `redis-cli GET system:throttle_mode` 返回值 |

### 25. 致命熔断（Redis OOM） [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `node-red-data-boundary.md` 2.2 |
| **风险** | Redis 内存溢出 → 缓存数据丢失 / 状态机崩溃 |
| **命令/方法** | `docker exec -it robot-platform-redis redis-cli DEBUG OOM` |
| **通过标准** | 系统自动进入 Safe-mode：`system:safe_mode=REDIS_OOM`，**停止所有自动化派单**，已执行订单继续，飞书/企微收到 🔴 致命熔断告警，含 `docker restart robot-platform-redis` 命令 |
| **佐证** | `redis-cli GET system:safe_mode` 返回值 + Node-RED 新派单全部返回 `503 Service Unavailable` |

### 26. SQLite WAL 防午夜卡顿 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `node-red-data-boundary.md` 1.1 |
| **风险** | WAL 文件过大 → checkpoint 阻塞写入 |
| **命令/方法** | 前置检查：`sqlite3 robot_platform.db "SELECT page_count * page_size as wal_size FROM pragma_wal_checkpoint() JOIN pragma_page_size();"`<br>若 < 100MB：`PRAGMA wal_checkpoint(TRUNCATE);`<br>若 ≥ 100MB：改用 `PRAGMA wal_checkpoint(PASSIVE);` + 凌晨归档 |
| **通过标准** | TRUNCATE 执行时间 < 2 秒，期间 HTTP 接口仍响应（用 `curl` 并行探测），WAL 大小回归正常 |
| **佐证** | `sqlite3` 执行时间截图 + 并行 `curl` 响应时间 < 500ms |

### 27. 高频表 ID 溢出防护 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `node-red-data-boundary.md` 1.1 |
| **风险** | `AUTOINCREMENT` 导致 INT 溢出 → 数据库写入失败 |
| **命令/方法** | `sqlite3 robot_platform.db ".schema orders" \| grep -i autoincrement` |
| **通过标准** | 高频表（orders, outbox_events, trace_log）**禁用** `AUTOINCREMENT`，使用 `INTEGER PRIMARY KEY`（64 位，理论上限 9e18，足够 100 年） |
| **佐证** | Schema 截图确认无 `AUTOINCREMENT` 关键字 |

### 28. 30 天冷数据归档 [P2]

| 属性 | 内容 |
|------|------|
| **来源** | `node-red-data-boundary.md` 1.1 |
| **风险** | 数据库膨胀 → 查询性能下降 / 备份耗时过长 |
| **命令/方法** | 检查归档脚本：`ls -la /app/scripts/archive_old_data.sh && cat /app/scripts/archive_old_data.sh` |
| **通过标准** | 脚本存在且可执行，逻辑为：将 30 天前 `trace_log` / `heartbeat_history` 压缩上传 OSS，本地执行 `VACUUM`，**保留 180 天内数据**（等保要求） |
| **佐证** | 脚本执行日志 + OSS 控制台存在归档文件 |

---

## 🛡️ 维度六：物理级防呆（4 项）

### 29. settings.js Git 提交拦截（异步非阻塞） [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `docker-infra-patterns.md` 2.1（v3.4 修正） |
| **风险** | 同步 Git 检查阻塞事件循环 → 所有机器人心跳中断 |
| **命令/方法** | 在 `/data` 目录创建 10GB 临时文件（`dd if=/dev/zero of=/data/bigfile bs=1M count=10240`），点击 Node-RED Deploy |
| **通过标准** | 2 秒内返回 `403 {"error":"请先提交 Git！"}`，`docker stats` 看 Node-RED CPU 无飙升，**机器人心跳不中断**（用 MQTT 客户端观察心跳间隔仍 ≤ 5s） |
| **佐证** | Deploy 响应时间截图 + MQTT 心跳时间线无断点 |

### 30. 禁用危险操作快捷键 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `docker-infra-patterns.md` 2.2 |
| **风险** | 误触 Delete 键批量删除节点 → 生产流程瘫痪 |
| **命令/方法** | 登录 Node-RED Editor，尝试按 `Delete` 键删除节点，观察是否弹窗确认 |
| **通过标准** | 快捷键已禁用或触发二次确认弹窗："这将删除选中节点及其所有连线，确定吗？"，**无一键删除** |
| **佐证** | Node-RED `settings.js` 中 `editorTheme.actions` 配置截图 |

### 31. Import/Export 心理防线 [P2]

| 属性 | 内容 |
|------|------|
| **来源** | `docker-infra-patterns.md` 2.3 |
| **风险** | 误导入旧版 flows.json → 配置回滚 |
| **命令/方法** | 点击 Node-RED 菜单 "导入" → "剪贴板" |
| **通过标准** | 弹窗确认："这将覆盖当前所有节点，确定吗？（建议先导出备份）"，**不禁止导入，但增加心理防线** |
| **佐证** | 弹窗截图 |

### 32. 急救大屏 IP 白名单 + API 保护 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `rescue-dashboard.md` 第 2 条（v3.4 修正） |
| **风险** | 非授权人员触发安全模式 / 伪造 x-forwarded-for 绕过 |
| **命令/方法** | 分别测试 4 个场景：<br>1. 非白名单 IP 访问 `http://nodered:1880/dashboard/rescue?ops_phone=13812345678`<br>2. 非白名单 IP `curl -X POST http://nodered:1880/api/safe-mode`<br>3. 伪造 Header `curl -H "x-forwarded-for: 127.0.0.1" http://外网IP/dashboard/rescue`<br>4. 白名单 IP 正常访问 |
| **通过标准** | 场景 1/2/3 全部返回 `403 Forbidden`，场景 4 返回 200 且 HTML 中 `ops_phone` 已转义（源码中无 `<script>` 注入） |
| **佐证** | 4 个场景的 HTTP 响应截图 + HTML 源码中 `ops_phone` 为纯文本节点 |

---

## 📜 维度七：合规与审计（4 项）

### 33. 审计日志 6 个月留存 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `compliance-checklist.md` / `000-global-iron-rules.mdc` 第 9 条 |
| **风险** | 清理 180 天内数据 → 等保测评不通过 / 行政处罚 |
| **命令/方法** | 尝试执行清理：`DELETE FROM trace_log WHERE created_at < datetime('now', '-179 days');` |
| **通过标准** | 系统拒绝执行，返回 `"等保合规：180 天内数据禁止清理"`，`trace_log` / `audit_log` 表 179 天前数据仍然存在 |
| **佐证** | SQL 执行报错截图 + `SELECT COUNT(*) FROM trace_log WHERE created_at < datetime('now', '-179 days');` 结果 > 0 |

### 34. 等保三级-密码复杂度 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `compliance-checklist.md` |
| **风险** | 弱密码被爆破 → 管理后台沦陷 |
| **命令/方法** | Node-RED Admin 创建用户：`admin` / `123456` |
| **通过标准** | `adminAuth` 拒绝创建，提示 `"密码必须 ≥8 位，含大小写+数字+特殊字符"`，无法保存 |
| **佐证** | Node-RED 创建用户界面报错截图 |

### 35. 等保三级-双因素认证 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | `compliance-checklist.md` |
| **风险** | 仅密码登录 → 管理员身份被盗用 |
| **命令/方法** | 登录 Node-RED 管理后台（`http://nodered:1880`） |
| **通过标准** | 输入密码后**强制要求**第二因素：TOTP 验证码（如 Google Authenticator）或企业微信扫码，**无法仅密码进入** |
| **佐证** | 登录流程录屏（从输入密码到要求 TOTP） |

### 36. 等保三级-数据库内网访问 [P2]

| 属性 | 内容 |
|------|------|
| **来源** | `compliance-checklist.md` |
| **风险** | 数据库暴露公网 → 数据泄露 |
| **命令/方法** | `nmap -p 3306,5432,6379,8080 <公网IP>` |
| **通过标准** | 所有数据库端口（MySQL 3306 / PostgreSQL 5432 / Redis 6379 / Node-RED 1880）在公网 IP 显示 `filtered` 或 `closed`，仅监听 `127.0.0.1` 或内网 IP（如 `10.x.x.x` / `172.x.x.x` / `192.168.x.x`） |
| **佐证** | `nmap` 扫描结果截图 + `netstat -tlnp` 显示绑定地址 |

---

## 🚑 维度八：运维与急救（4 项）

### 37. 安全模式自动触发与恢复 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `040-ops-rescue.mdc` 第 1 条 |
| **风险** | 异常时未止血 → 雪崩扩大 |
| **命令/方法** | 模拟异常：停止 Redis 容器 `docker stop robot-platform-redis`，观察 30 秒内系统反应 |
| **通过标准** | 系统自动进入 Safe-mode，新派单停止，已执行订单继续，飞书告警 `"系统进入安全模式，原因：Redis 失联"`，恢复 Redis 后需**人工点击** `"恢复正常运行"` 按钮（非自动恢复，防误恢复） |
| **佐证** | `redis-cli GET system:safe_mode` 返回值 + 飞书告警时间线 |

### 38. 降级演练 3/7/14 天 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `040-ops-rescue.mdc` 第 4 条 / `degradation-drill-sop.md` |
| **风险** | 未演练即上线 → 真故障时不会用 |
| **命令/方法** | 上线前第 3 天：模拟断网（`iptables -A INPUT -j DROP`），强制使用纸质单补录 |
| **通过标准** | 补录准确率 **100%**（0 笔错漏），吞吐量 ≥ 正常 50%，**30 分钟内**恢复自动化，仓库主管签字确认 |
| **佐证** | 纸质单扫描件 + 补录后 `orders` 表与纸质单 100% 匹配脚本结果 |

### 39. 通知聚合与紧急穿透 [P1]

| 属性 | 内容 |
|------|------|
| **来源** | `notification-traffic-control.md` |
| **风险** | 50 台车断网产生 50 条告警 → 通知轰炸 / 真正碰撞告警被淹没 |
| **命令/方法** | 脚本模拟：<br>1. 50 台车同时断网（MQTT 断开）<br>2. 1 台车发生碰撞（`error_type='COLLISION'`） |
| **通过标准** | 断网告警**聚合为 1 条**（5 分钟滑动窗口内），碰撞告警**立即单独发送**（不聚合、不限流），飞书/企微在 3 秒内收到碰撞告警 |
| **佐证** | 飞书消息列表截图：1 条聚合断网 + 1 条独立碰撞 |

### 40. 双通道审批撕裂（乐观锁） [P2]

| 属性 | 内容 |
|------|------|
| **来源** | `human-loop-notification-matrix.md` 第 2 条 |
| **风险** | 飞书和企微同时审批 → 重复派单 |
| **命令/方法** | 同一笔 `SUSPENDED` 订单，飞书和企微两个管理员**同时点击** `"批准继续"` |
| **通过标准** | 先到者成功（订单转 `EXECUTING`），后到者收到 `"该订单已处理，状态：EXECUTING"`，`orders` 表无重复派单记录 |
| **佐证** | `orders` 表 `version` 字段递增 1（乐观锁生效），仅 1 条执行记录 |

---

## 🎯 验收签字页

### 三方在场确认

| 角色 | 姓名 | 签字 | 日期 | 备注 |
|------|------|------|------|------|
| 运维负责人 | | | | 负责基础设施、Docker、网络、数据库 |
| 开发负责人 | | | | 负责 Node-RED、SAP 桥接层、机器人适配 |
| 仓库主管 | | | | 负责业务验证、纸质单流程、急救页测试 |

### 最终裁决

- [ ] **全部 P0 项通过**（17/17）
- [ ] **P1 项通过率 ≥ 95%**（≥ 16/17，允许最多 1 项有条件通过）
- [ ] **P2 项通过率 ≥ 90%**（≥ 3/3，或最多 1 项未通过并记录风险）
- [ ] **版本校验**：`.cursor/rules/VERSION` = `v3.4`
- [ ] **Git 提交**：本次所有配置变更已 Commit，Commit Hash：`________________`

**上线许可**：

> 经三方联合验收，上述 36 项检查中，P0 全部通过，P1 通过 ____ 项，P2 通过 ____ 项。  
> 已知风险：________________________________________________  
> 风险缓解措施：______________________________________________  
> 
> **批准上线** ⬜  **延迟修复后上线** ⬜  **禁止上线** ⬜

---

## 📎 附录：快速命令参考

```bash
# 1. 一键检查所有容器状态
docker ps --format "table {{.Names}}	{{.Status}}	{{.Ports}}"

# 2. 一键检查数据库连接池
sqlite3 robot_platform.db "SELECT count(*) FROM sqlite_master WHERE type='table';"

# 3. 一键检查 Redis 内存
redis-cli INFO memory | grep used_memory_human

# 4. 一键检查 Node-RED 事件循环健康
curl -s http://nodered:1880/api/system-health | jq .

# 5. 一键触发安全模式（仅白名单 IP）
curl -X POST http://nodered:1880/api/safe-mode

# 6. 一键检查版本一致性
cat .cursor/rules/VERSION && curl -s http://nodered:1880/api/version

# 7. 一键检查最近 10 条异常
sqlite3 robot_platform.db "SELECT timestamp, level, message FROM trace_log ORDER BY id DESC LIMIT 10;"

# 8. 一键检查死信队列
sqlite3 robot_platform.db "SELECT count(*) FROM dead_letter_queue WHERE status='UNRESOLVED';"
```

---

> **文档版本**：v3.4  
> **最后更新**：2026-06-02  
> **下次评审**：上线后 30 天 / 发生重大故障后 / 版本升级前
