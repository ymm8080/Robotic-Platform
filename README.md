# SAP-EWM 机器人调度平台

> **工业级容错 + 物理级防呆 + 人性化降级**

## v5.0 异构融合 (开发中)

v5.0 基于 Open-RMF 架构重构，将多品牌 VDA5050/MQTT 机器人统一到一个协调器：

| 模块 | 说明 |
|------|------|
| `core/` | RCS 核心（FixedLaneMap、FleetAdapter、Safety、Scheduling、Survival） |
| `traffic_coordinator_v5/` | 交通协调器（地图加载、品牌适配器引导、YAML 设施地图） |
| `sap-bridge/` | SAP EWM ↔ 机器人桥接（品牌策略、MQTT 发布、VDA5050 协议） |
| `dashboard/` | React/TypeScript 控制面板（机器人列表、交通灯、区域锁定、告警） |
| `gateway/` | Node-RED 网关（审计日志、健康检查） |

**当前开发分支**: `DS-V4-Pro`
**修复日志**: [`D:/EWM ROBOT/fixing codes/fixed-log.md`](../fixing codes/fixed-log.md)

### 已完成的阶段性工作

| 阶段 | 状态 | 内容 |
|------|------|------|
| Phase 0 | ✅ | 构建/测试/打包修复（8 项） |
| Phase 1 | ✅ | v5.0 协调器可导入、可配置（YAML 地图、引导程序） |
| Phase 2 | ✅ | VDA5050/MQTT 对接 v5.0 协调器（6 品牌适配器、REST API） |
| Phase 3 | ✅ | Dashboard v5.0 扩展（平台状态 Hook、交通灯面板、区域锁定面板） |
| Phase 4 | ✅ | 文档（修复日志、README 更新） |

## 快速启动

```bash
# 1. 准备环境
cp .env.example .env
vim .env  # 填入真实值

echo "your-sap-password" > secrets/sap_password.txt
chmod 600 secrets/sap_password.txt

# 2. 启动全栈
docker compose up -d --build

# 3. 验证
curl http://localhost:1880/api/system-health
```

## 自动修复和监控系统

### 自动修复脚本

项目包含一个综合性的自动修复脚本，可修复所有AI代码审查中发现的问题：

```bash
# 运行综合修复脚本
python auto_fix_all.py

# 只运行健康检查
python auto_fix_all.py --once

# 查看帮助
python auto_fix_all.py --help
```

**修复范围**:
- `sap-bridge/auth.py`: 线程安全、错误处理、Redis连接关闭
- `sap-bridge/clients/zewm_robco_client.py`: SQL注入防护、配置验证、错误响应解析
- `traffic_coordinator_v5/simulator/fleet.py`: 异常日志改进
- `traffic_coordinator_v5/simulator/cli.py`: 导入顺序修复
- Grafana仪表板配置修复
- SAP协调器桥接改进

### CatPaw进程监控系统

解决CatPaw窗口停止运行问题，提供自动重启机制：

```bash
# 1. 快速安装
setup_catpaw_monitor.bat

# 2. 启动监控
python monitor_catpaw.py

# 3. 一次性健康检查
python monitor_catpaw.py --once

# 4. 创建Windows任务计划（管理员权限）
python monitor_catpaw.py --create-task
# 然后在PowerShell中运行：
schtasks /create /xml "catpaw_monitor_task.xml" /tn "CatPawMonitor"
```

**监控功能**:
- ✅ 进程状态监控（PID检查）
- ✅ HTTP健康检查
- ✅ 自动重启（可配置延迟）
- ✅ 重启限制（每小时最大次数）
- ✅ 日志轮转（10MB自动切割）
- ✅ Windows任务计划集成
- ✅ 启动文件夹快捷方式

**配置文件**: `catpaw_monitor_config.json`
**日志文件**: `catpaw_monitor.log`, `catpaw_alerts.log`

## 开发工具

### 代码质量检查

```bash
# 运行代码检查
python -m ruff check --fix .

# 运行测试
python -m pytest sap-bridge/tests/ -v

# 清理临时文件
cleanup_temp_files.bat
```

### Git工作流

```bash
# 提交修复
git add -A
git commit -m "fix: apply AI review fixes"

# 推送更改
git push origin feat/auto-impl-sap-zewm-20260711-234536
```

## 文档

- [部署指南](docs/DEPLOY_GUIDE_v3.4.md)
- [48小时检查清单](docs/48h-checklist-v3.4.md)（39项）
- [架构清单](docs/CURSOR_ARCHITECTURE_MANIFEST_v3.4.md)
- [NTP时钟同步](docs/APPENDIX_NTP.md)
- [告警通道降级](docs/APPENDIX_NOTIFICATION.md)
- [灾难恢复演练](docs/APPENDIX_BACKUP.md)

## 版本

- v3.4 FINAL — 2026-06-02（稳定版，生产环境）
- v5.0 开发中 — 2026-07（异构融合架构，分支 `DS-V4-Pro`）
- **自动修复系统**: v1.0 — 2026-07-13（AI代码审查自动修复）
- **进程监控**: v1.0 — 2026-07-13（CatPaw自动重启）

## 紧急恢复

如果CatPaw窗口停止运行：
```bash
# 手动重启所有服务
restart_catpaw.bat

# 或使用监控系统
python monitor_catpaw.py
```

**注意**: 监控系统需要以下Python包：
```bash
pip install psutil requests
```