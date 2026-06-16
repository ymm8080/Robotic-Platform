# SAP-EWM 机器人调度平台 Watchdog 集成部署指南 v3.4

> **版本**：v3.4  
> **适用**：生产环境首次部署 / 大版本升级  
> **前提**：Docker Engine >= 24.0, Docker Compose >= 2.20, Linux 内核 >= 5.4

---

## 📦 文件清单

```
robot-platform-v3.4/
├── docker-compose.yml              # 主编排文件（8 个服务）
├── .env.example                    # 环境变量模板（必须修改后重命名为 .env）
├── .cursor/
│   └── rules/
│       └── VERSION                 # v3.4（启动校验用）
├── watchdog/
│   ├── Dockerfile                  # Watchdog 容器构建文件
│   ├── requirements.txt            # Python 依赖
│   ├── config.yaml                 # 静态配置（限流阈值、告警模板）
│   └── watchdog.py                 # 主程序（动态限流 + 熔断 + 安全模式）
├── nginx/
│   ├── rescue-dashboard-offline.html  # 独立急救页（Node-RED 崩溃时仍可用）
│   └── nginx.conf                  # Nginx 配置（静态文件 + 反向代理）
├── redis/
│   └── redis.conf                  # AOF OOM 防护配置（maxmemory 256MB）
├── secrets/
│   └── sap_password.txt            # SAP 密码（chmod 600，禁止入 Git）
├── sql/
│   ├── init.sql                    # 数据库初始化（表结构 + 索引）
│   └── migrations/                 # 版本迁移脚本（按序号执行）
├── nodered/
│   ├── settings.js                 # Node-RED 配置（Git 拦截、IP 白名单、安全函数注入）
│   └── flows.json                  # 流程文件（由 Node-RED 生成，Git 管理）
├── sap-bridge/
│   ├── main.py                     # FastAPI 主程序
│   ├── requirements.txt
│   └── sapnwrfc.ini                # SAP NW RFC SDK 配置
└── mqtt/
    └── mosquitto.conf              # MQTT Broker 配置（认证 + ACL）
```

---

## 🚀 快速部署（5 分钟）

### Step 1：准备环境

```bash
# 1. 克隆仓库（或解压部署包）
cd /opt/robot-platform

# 2. 创建必要目录
mkdir -p secrets sql/migrations nodered sap-bridge mqtt nginx redis watchdog logs

# 3. 复制环境变量模板并修改
mv .env.example .env
vim .env
# 必须修改：
# - RESCUE_OPS_PHONE（真实 11 位手机号）
# - RESCUE_DASHBOARD_ALLOWED_IPS（主管电脑 IP）
# - SAP_ASHOST / SAP_SYSNR / SAP_CLIENT / SAP_USER
# - FEISHU_WEBHOOK_URL（可选，但强烈建议配置）

# 4. 创建 SAP 密码文件（禁止硬编码）
echo "YOUR_SAP_PASSWORD" > secrets/sap_password.txt
chmod 600 secrets/sap_password.txt
```

### Step 2：构建 Watchdog 镜像

```bash
# Watchdog 需要独立构建（因包含 docker CLI）
docker compose build watchdog
```

### Step 3：启动全栈（按依赖顺序）

```bash
# 前台启动（首次部署建议前台观察日志）
docker compose up --build

# 或后台启动（生产环境）
docker compose up -d --build

# 查看启动状态
docker compose ps
```

### Step 4：验证核心服务健康

```bash
# 1. 检查所有容器状态
docker compose ps
# 预期：nodered, sap-bridge, redis, watchdog, nginx-rescue, mqtt 全部 Up (healthy)

# 2. 检查 Redis 内存限制
docker exec robot-platform-redis redis-cli INFO memory | grep maxmemory
# 预期：maxmemory:268435456 (256MB)

# 3. 检查 Watchdog 运行状态
docker logs robot-platform-watchdog --tail 20
# 预期："🐕 SAP-EWM Watchdog v3.4 启动" + 周期性巡检日志

# 4. 检查 Node-RED 版本校验
docker logs robot-platform-nodered --tail 20
# 预期："✅ 版本校验通过：v3.4"

# 5. 检查急救页独立可用
curl -I http://localhost:8080
# 预期：HTTP/1.1 200 OK（来自 Nginx，非 Node-RED）
```

---

## 🔧 关键配置说明

### 1. Watchdog 独立进程（核心变更 v3.4）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CPU_THRESHOLD` | 80 | CPU 超过此值且 Checkpoint > 5s 触发限流 |
| `CHECKPOINT_THRESHOLD` | 5000 | SQLite WAL checkpoint 耗时阈值（ms） |
| `THROTTLE_RATE_MIN` | 10 | 限流绝对下限（单/秒） |
| `NORMAL_RATE_DEFAULT` | 50 | 历史正常峰值（Node-RED 运行后可动态更新） |
| `SAFE_MODE_TRIGGER_REDIS_OOM` | true | Redis OOM 时自动进入安全模式 |
| `SAFE_MODE_TRIGGER_NODERED_UNHEALTHY` | true | Node-RED 不健康时自动进入安全模式 |

**限流逻辑**：
- CPU > 80% 且 Checkpoint > 5000ms → 限流至历史峰值的 30%（但不低于 10 单/秒）
- Checkpoint > 10000ms → 进一步降至 15 单/秒
- 连续 3 次巡检正常（CPU < 64% 且 Checkpoint < 4000ms）→ 自动解除限流

**熔断逻辑**：
- Redis OOM（used_memory > 95% maxmemory 或 evicted_keys > 100）→ 安全模式
- Node-RED 容器状态非 healthy → 安全模式
- 安全模式下：停止所有新派单，已执行订单继续，需人工恢复

### 2. 急救页双保险架构

```
用户浏览器
    │
    ├─→ http://IP:8080  ──→ Nginx 独立容器（静态 HTML，Node-RED 崩溃时仍可用）
    │                         └─ 轮询 http://IP:1880/api/system-health
    │
    └─→ http://IP:1880  ──→ Node-RED（崩溃时 TCP 连接失败）
```

**主管电脑配置**：
1. 浏览器首页设为 `http://<服务器IP>:8080/?ops_phone=13812345678`
2. 打印二维码贴在显示器右下角
3. 培训话术：**"如果机器人全停了或者乱跑，先点红色按钮，再打电话！"**

### 3. Redis AOF OOM 防护

```
maxmemory 256mb          # 硬上限（含 fork 开销约 300MB）
maxmemory-policy allkeys-lru  # 优先淘汰冷数据
appendonly yes           # AOF 持久化
aof-use-rdb-preamble yes # RDB + AOF 混合，加速恢复
```

**OOM 时行为**：
- Redis 开始驱逐键 → Watchdog 检测到 evicted_keys 突增 → 触发安全模式
- 同时飞书告警含 `docker restart robot-platform-redis` 命令
- 重启后 AOF + RDB 混合恢复，数据不丢失

### 4. 多仓部署隔离

每个仓库独立一套 `.env` + `docker-compose.yml`（或同文件不同分支）：

```bash
# 1 号仓（W01）
WAREHOUSE_ID=W01
NODE_RED_EXTERNAL_PORT=1880
SAP_CLIENT=100

# 2 号仓（W02）
WAREHOUSE_ID=W02
NODE_RED_EXTERNAL_PORT=1881
SAP_CLIENT=200
```

**绝对禁止**：多个仓共用同一个 `robot_platform.db` 文件或同一个 Redis DB。

---

## 🧪 核心验证命令（部署后必做）

### 验证 1：Watchdog 限流触发

```bash
# 在 Node-RED 中注入死循环（模拟事件循环阻塞）
# 方法：Deploy 一个 Function 节点，内部写 while(true) {}

# 观察 Watchdog 日志
docker logs -f robot-platform-watchdog
# 预期 10 秒内出现：
# "🟡 动态限流：限流至 15 单/秒"

# 检查 Redis 标志位
docker exec robot-platform-redis redis-cli GET system:throttle_mode
# 预期："15"

# 检查 Node-RED 是否读取到限流标志
curl http://localhost:1880/api/system-health | jq .throttle_mode
# 预期：true
```

### 验证 2：Redis OOM 熔断

```bash
# 模拟 Redis OOM（仅测试环境！）
docker exec robot-platform-redis redis-cli DEBUG OOM

# 观察 Watchdog 日志
# 预期："🔴 致命熔断：进入安全模式，原因: REDIS_OOM"

# 检查安全模式标志
docker exec robot-platform-redis redis-cli GET system:safe_mode
# 预期："REDIS_OOM"

# 检查 Node-RED 新派单是否被拒绝
curl -X POST http://localhost:1880/api/orders -d '{"test":true}'
# 预期：503 Service Unavailable

# 恢复
docker restart robot-platform-redis
docker exec robot-platform-redis redis-cli DEL system:safe_mode
```

### 验证 3：急救页离线兜底

```bash
# 1. 正常打开急救页（Nginx 端口 8080）
open http://localhost:8080
# 预期：显示 "🟢 系统正常运行"

# 2. 停止 Node-RED（模拟崩溃）
docker stop robot-platform-nodered

# 3. 不刷新页面，等待 5 秒
# 预期：页面自动切换为 "⚠️ Node-RED 离线"，显示 curl 命令和运维电话

# 4. 恢复 Node-RED
docker start robot-platform-nodered
```

### 验证 4：Git 提交拦截（异步非阻塞）

```bash
# 在 Node-RED /data 目录创建大文件
docker exec robot-platform-nodered dd if=/dev/zero of=/data/bigfile bs=1M count=1024

# 在 Editor 中点击 Deploy
# 预期：2 秒内返回 403 {"error":"请先提交 Git！"}

# 验证机器人心跳不中断（用 MQTT 客户端观察）
# 预期：心跳间隔仍 ≤ 5 秒，无断点

# 清理
docker exec robot-platform-nodered rm /data/bigfile
```

### 验证 5：IP 白名单（4 场景）

```bash
# 场景 1：非白名单 IP 访问急救页
curl -H "X-Forwarded-For: 8.8.8.8" http://localhost:1880/dashboard/rescue
# 预期：403 Forbidden

# 场景 2：非白名单 IP 直接调安全模式 API
curl -X POST -H "X-Forwarded-For: 8.8.8.8" http://localhost:1880/api/safe-mode
# 预期：403 Forbidden

# 场景 3：伪造 x-forwarded-for 从外网访问
curl -H "X-Forwarded-For: 127.0.0.1" http://localhost:1880/dashboard/rescue
# 预期：403 Forbidden（因 direct IP 不在信任代理列表）

# 场景 4：白名单 IP 正常访问
curl -H "X-Forwarded-For: 10.0.1.100" http://localhost:1880/dashboard/rescue
# 预期：200 OK，且 HTML 中 ops_phone 为纯文本（无 XSS）
```

---

## 📊 日常运维命令速查

```bash
# 查看所有服务状态
docker compose ps

# 查看实时日志（按服务）
docker compose logs -f noderen
docker compose logs -f watchdog
docker compose logs -f sap-bridge

# 进入安全模式（人工触发）
curl -X POST http://localhost:1880/api/safe-mode

# 解除安全模式
curl -X POST http://localhost:1880/api/restore-mode

# 手动清理旧日志（触发限流时运维操作）
docker exec robot-platform-nodered bash /app/scripts/cleanup_old_logs.sh

# SQLite WAL 手动截断（业务低谷期执行）
docker exec robot-platform-nodered sqlite3 /data/robot_platform.db "PRAGMA wal_checkpoint(TRUNCATE);"

# Redis 大键扫描（OOM 排查）
docker exec robot-platform-redis redis-cli --bigkeys

# 检查死信队列
sqlite3 /var/lib/docker/volumes/robot-platform_nodered-data/_data/robot_platform.db   "SELECT COUNT(*) FROM dead_letter_queue WHERE status='UNRESOLVED';"

# 一键备份（上线前/升级前必做）
docker compose exec nodered tar czf /tmp/nodered-backup-$(date +%Y%m%d).tar.gz /data
docker compose cp nodered:/tmp/nodered-backup-$(date +%Y%m%d).tar.gz ./backups/
```

---

## ⚠️ 上线前强制检查（36 项清单）

详见 `docs/48h-checklist-v3.4.md`，必须三方签字确认后方可上线。

---

## 🆘 故障排查

| 现象 | 排查命令 | 解决方案 |
|------|---------|---------|
| Node-RED 无法启动 | `docker logs robot-platform-nodered` | 检查 VERSION 文件是否存在、settings.js 语法 |
| Watchdog 不断重启 | `docker logs robot-platform-watchdog` | 检查 Redis 是否可达、docker.sock 权限 |
| Redis 内存爆满 | `redis-cli INFO memory` | 执行 `redis-cli DEBUG OOM` 触发安全模式，重启 Redis |
| 急救页显示离线 | `curl http://localhost:8080` | 检查 nginx-rescue 容器是否运行 |
| SAP 连接泄漏 | SM04 事务码 | 检查 sap-bridge 日志，确认 `finally: close()` |
| 限流不解除 | `redis-cli GET system:throttle_mode` | 检查 CPU 是否持续 > 64%，手动 `DEL system:throttle_mode` |

---

> **文档版本**：v3.4  
> **最后更新**：2026-06-02  
> **维护团队**：机器人调度平台运维组
