# SAP-EWM 机器人调度平台 Cursor 配置架构清单 v3.4

> **文档版本**：v3.4 FINAL  
> **适用对象**：开发团队、运维团队、等保审计人员  
> **生成日期**：2026-06-02  
> **维护责任**：机器人调度平台架构组

---

## 一、架构总览

### 1.1 设计哲学

本配置采用 **"宪法-法律-判例"** 三级架构：

| 层级 | 对应文件 | 变更频率 | 违反后果 |
|------|---------|---------|---------|
| **宪法** | `.cursor/rules/*.mdc` | 极少（季度评审） | AI 直接拒绝执行 |
| **法律** | `.cursor/skills/**/*.md` | 中频（月度更新） | AI 生成前自动校验 |
| **判例** | `.cursor/agents/*.md` | 按需（问题驱动） | 特定场景强制引用 |

### 1.2 九维防御体系

```
┌─────────────────────────────────────────────────────────────┐
│  维度1: 宪法规则 (5个.mdc)      → AI行为红线，不可逾越       │
│  维度2: 领域知识 (25个Skills)   → 技术细节，按需加载         │
│  维度3: 专属代理 (6个Agents)    → 角色隔离，冲突仲裁         │
│  维度4: 动态工具 (5个MCP)       → 外部能力，默认禁用         │
│  维度5: 安全防护 (3个文件)      → 项目边界，防误触           │
│  维度6: 深水区   (10个补丁)     → 极端场景，经验盲区         │
│  维度7: 物理防呆 (4层)          → 人机交互，最后一道防线     │
│  维度8: 非代码盲区 (3项)        → 时钟/通知/备份             │
│  维度9: 容器编排 (9个服务)      → 运行时保障，独立进程       │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、宪法级规则 (.cursor/rules/)

### 2.1 规则文件清单

| 文件名 | 权重 | 适用范围 | 核心约束 | 变更记录 |
|--------|------|---------|---------|---------|
| `000-global-iron-rules.mdc` | alwaysApply | 全局 | LLM禁令、急停硬接线、位移互锁、数据主权、凭证管理、时区统一、版本校验 | v3.3→v3.4: 新增第8条语言边界、第9条版本合规 |
| `010-nodered-core.mdc` | `**/flows.json`, `**/*.js` | Node-RED核心 | Catch闭环、状态机、Outbox双写、入库拒收、区域锁、热更新灰度、msg防御 | 无变更 |
| `020-sap-bridge.mdc` | `**/sap-bridge/**/*.py`, `**/Dockerfile` | SAP桥接层 | 禁用Alpine、异步队列、pyrfc连接管理、异常友好化 | 无变更 |
| `030-robot-device.mdc` | `**/robots/**/*.py`, `**/mqtt*`, `**/subflows/**` | 机器人适配 | 统一入参、电量限制、环境染色、位移死锁、人机安全、API偏差、OTA管控 | v3.3→v3.4: 新增第7条厂商API升级管控 |
| `040-ops-rescue.mdc` | `**/*.sh`, `**/crontab`, `**/rsync*` | 运维排障 | 安全模式优先、恐慌词库、补录乐观锁、降级演练 | v3.3→v3.4: 更新panic词库 |

### 2.2 规则优先级与冲突仲裁

```
冲突发生时，按以下优先级裁决：
1. 000-global-iron-rules.mdc（全局铁律，绝对优先）
2. 010-nodered-core.mdc（主板规范，领域优先）
3. 020/030/040（各子系统规范）
4. .cursor/skills/（具体实现细节）

仲裁人：_orchestrator.md（Agent编排器）
```

### 2.3 版本校验机制

```yaml
# 启动时强制校验
校验源: .cursor/rules/VERSION
运行时版本: settings.js 中 RUNTIME_VERSION = 'v3.4'
校验逻辑: 
  - 文件不存在 → 进程退出(FATAL)
  - 版本不一致 → 进程退出(FATAL)
  - 校验通过 → 日志输出 "✅ 版本校验通过：v3.4"
```

---

## 三、领域知识库 (.cursor/skills/)

### 3.1 知识分层

```
.cursor/skills/
├── architecture/          # 大框架，季度评审
│   ├── vda-5050-adapter-design.md
│   ├── event-driven-outbox.md
│   ├── node-red-data-boundary.md        # v3.4更新：性能熔断与动态限流
│   ├── human-loop-notification-matrix.md
│   └── compliance-checklist.md          # v3.4新增：等保2.0三级
├── implementation/        # 具体实现，月度更新
│   ├── node-red-lowcode-patterns.md     # v3.4更新：安全函数与隐式循环阻断
│   ├── nodered-debug-interpretation.md
│   ├── flow-integrity-check.md
│   ├── robot-firmware-ota.md            # v3.4新增
│   ├── schema-migration-automation.md
│   ├── data-masking-gateway.md
│   └── llm-exception-noise-reduction.md
└── operations/            # 运维与组织，季度更新
    ├── docker-infra-patterns.md         # v3.4更新：settings.js物理级防误触
    ├── notification-traffic-control.md
    ├── degradation-drill-sop.md
    ├── cost-budget-sentinel.md
    ├── robot-api-deviation-tracking.md
    ├── implementation-roadmap.md        # v3.4更新：多仓隔离
    ├── rescue-dashboard.md              # v3.4更新：离线fallback+IP白名单
    ├── language-boundary-contract.md    # v3.4新增
    ├── physical-digital-friction.md
    ├── device-health-profiling.md
    ├── nodered-git-workflow.md
    ├── prompt-version-control.md
    └── wcs-shadow-sandbox.md
```

### 3.2 知识激活条件

| 文件 | 激活场景 | 被谁引用 |
|------|---------|---------|
| `vda-5050-adapter-design.md` | 用户要求适配新品牌机器人 | robot-adapter-writer.md |
| `event-driven-outbox.md` | 用户要求修改状态机或事务逻辑 | node-red-core-builder.md |
| `node-red-data-boundary.md` | 用户提到性能、卡顿、内存问题 | node-red-core-builder.md |
| `rescue-dashboard.md` | 用户恐慌（"崩了/挂了/怎么办"） | ops-rescuer.md |
| `compliance-checklist.md` | 用户提到等保、审计、合规 | _orchestrator.md |

---

## 四、专属代理角色 (.cursor/agents/)

### 4.1 代理清单

| 代理 | 约束源 | 编程语言 | 工作模式 | 特殊权限 |
|------|--------|---------|---------|---------|
| `node-red-core-builder.md` | 010-nodered-core.mdc + architecture/ | JavaScript (ES6+) | 读写 | 主板规范优先权 |
| `sap-bridge-coder.md` | 020-sap-bridge.mdc + sap-ewm-odata-rfc.md | Python (3.11+) | 读写 | 无 |
| `robot-adapter-writer.md` | 030-robot-device.mdc + implementation/ | JavaScript (ES6+) | 读写 | 无 |
| `ops-rescuer.md` | 040-ops-rescue.mdc + rescue-dashboard.md | 无（只输出命令） | **只读不写** | 急救时独占模式 |
| `dify-feishu-architect.md` | human-loop-notification-matrix.md + notification-traffic-control.md | JavaScript/Python | 读写 | 双通道仲裁权 |
| `_orchestrator.md` | 全部规则 | 全部 | 协调 | 冲突仲裁权 |

### 4.2 代理冲突仲裁规则

```
场景：sap-bridge-coder 和 robot-adapter-writer 对 HTTP timeout 有冲突
裁决：以 node-red-core-builder 的主板规范为准

场景：ops-rescuer 正在工作（用户说"崩了/救命"）
裁决：其他 Agent 只读不写，ops-rescuer 独占输出

场景：跨领域请求（如"写一个从SAP接单到机器人派单的完整流程"）
裁决：_orchestrator 协调，按顺序调用 sap-bridge-coder → node-red-core-builder → robot-adapter-writer
```

---

## 五、动态工具 (MCP)

### 5.1 工具清单

| 工具 | 用途 | 启用条件 | 降级方案 |
|------|------|---------|---------|
| `mcp-server-sqlite` | 数据库查询 | 本地安装 uv | VS Code SQLite Viewer 插件 |
| `mcp-server-redis` | 缓存查询 | 本地安装 uv | `docker exec redis redis-cli` |
| `mcp-server-docker` | 容器管理 | Docker 已安装 | `docker logs` / `docker stats` |
| `mcp-server-fetch` | HTTP 请求 | 本地安装 uv | `curl` 命令 |
| `mcp-server-mqtt` | 消息订阅 | 本地安装 npx | MQTTX 客户端 |

### 5.2 安全策略

```yaml
默认状态: 禁用 (mcp.json.disabled)
启用条件: 
  - 本地已安装 uv (Python) 和 Node.js
  - 用户明确知道 MCP 是什么
风险: 不了解的用户启用后可能误操作生产数据库
防护: 文件后缀 .disabled，README 醒目标注 ⚠️ 警告
```

---

## 六、安全防护文件

| 文件 | 作用 | 内容 |
|------|------|------|
| `.cursorignore` | 防止 AI 读取敏感文件 | `secrets/`, `.env`, `*.db` |
| `.prettierignore` | 防止格式化破坏配置 | `flows.json`, `*.mdc` |
| `.cursor/rules/VERSION` | 版本校验源 | `v3.4` |

---

## 七、深水区补丁（经验盲区）

| 编号 | 问题 | 来源 | 补丁位置 |
|------|------|------|---------|
| 1 | 幽灵堵车（10秒无位移） | physical-digital-friction.md | 030-robot-device.mdc 第4条 |
| 2 | 位移与急停互锁 | 000-global-iron-rules.mdc | 第3条 |
| 3 | 环境染色（env_tag） | 030-robot-device.mdc | 第3条 |
| 4 | 入库拒收（weight=0） | 010-nodered-core.mdc | 第4条 |
| 5 | 通知聚合与穿透 | notification-traffic-control.md | 第1-4条 |
| 6 | 双通道审批撕裂 | human-loop-notification-matrix.md | 第2条 |
| 7 | 厂商API偏差 | 030-robot-device.mdc | 第6条 |
| 8 | OTA后API行为变更 | robot-firmware-ota.md | 第2条 |
| 9 | 配置热更新雪崩 | 010-nodered-core.mdc | 第7条 |
| 10 | 降级演练3/7/14天 | 040-ops-rescue.mdc | 第4条 |

---

## 八、物理级防呆

| 层级 | 实现 | 触发条件 | 恢复方式 |
|------|------|---------|---------|
| **settings.js拦截** | httpAdminMiddleware异步Git检查 | Deploy前未commit | 手动git commit后重试 |
| **运行时安全函数** | safeLoop/safeParse/safeExec注入 | 数组超限/JSON过大/函数超时 | 自动阻断，飞书告警 |
| **急救大屏** | Nginx独立容器+离线fallback | Node-RED崩溃 | 主管点击红色按钮+curl命令 |
| **IP白名单** | httpNodeMiddleware+CIDR匹配 | 非授权IP访问急救页 | 403 Forbidden |

---

## 九、非代码盲区（v3.4新增）

| 盲区 | 风险 | 修复方案 | 文档位置 |
|------|------|---------|---------|
| **NTP时钟漂移** | Redis TTL错乱、审计时序颠倒 | chrony+容器挂载+Watchdog检测 | APPENDIX_NTP.md |
| **告警通道单点** | 飞书宕机=全员失聪 | 4层降级：飞书→企微→短信→蜂鸣器 | APPENDIX_NOTIFICATION.md |
| **备份从未恢复** | 真灾难时无法救命 | 季度rm -rf演练+OSS恢复+30分钟验证 | APPENDIX_BACKUP.md |

---

## 十、版本演进记录

| 版本 | 日期 | 核心变更 | 评审轮次 |
|------|------|---------|---------|
| v1.0 | 2026-05-15 | 基础Node-RED+SQLite架构 | 1 |
| v2.0 | 2026-05-20 | 新增SAP桥接层+机器人适配 | 2 |
| v3.0 | 2026-05-25 | 引入Cursor规则体系+6个.mdc | 3 |
| v3.1 | 2026-05-28 | 新增深水区补丁+物理防呆 | 4 |
| v3.2 | 2026-05-30 | 急救大屏+IP白名单 | 5 |
| v3.3 | 2026-06-01 | 语言边界契约+OTA管控 | 6 |
| **v3.4** | **2026-06-02** | **Watchdog独立进程+Docker Socket代理+非代码盲区** | **7** |

---

## 十一、维护与评审

### 11.1 变更流程

```
1. 提出变更需求（Issue模板）
2. 影响分析（哪些.mdc/.md受影响）
3. 版本号评估（PATCH/MINOR/MAJOR）
4. 评审会议（三方：开发+运维+主管）
5. 修改文件 + 更新VERSION
6. 48小时检查清单重新执行受影响项
7. git tag + 发布说明
```

### 11.2 评审触发条件

- 季度例行评审（每3个月）
- 重大故障后（P0事件）
- 新品牌机器人接入前
- 等保测评前
- 版本升级前

---

> **文档结束**  
> 生成时间：2026-06-02 10:43  
> 生成工具：Cursor AI Assistant  
> 审核状态：待三方签字
