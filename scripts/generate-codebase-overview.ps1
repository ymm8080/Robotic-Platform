param()
$R = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES"
$DF = (Get-Date).ToString("yyyy-MM-dd")
$TS = (Get-Date).ToString("HH:mm:ss")
$outDir = "D:\EWM ROBOT\CODEBASE OVERVIEW"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
$outFile = Join-Path $outDir "CODEBASE OVERVIEW $DF V2.md"

Push-Location $R

# ============================================================
# HELPER FUNCTIONS
# ============================================================
function Get-FileCountByExt($dir, $ext) {
    $count = 0; $lines = 0
    if (Test-Path $dir) {
        $files = Get-ChildItem "$dir" -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -eq $ext -and $_.FullName -notmatch 'node_modules|\.git|__pycache__|dist' }
        $count = $files.Count
        $lines = ($files | ForEach-Object { (Get-Content $_.FullName -ErrorAction SilentlyContinue).Count } | Measure-Object -Sum).Sum
    }
    return @{count=$count; lines=$lines}
}

function Get-SimpleTree($dir, $maxDepth=2, $skipPatterns=@('node_modules','.git','__pycache__','dist')) {
    $result = @()
    if (-not (Test-Path $dir)) { return $result }
    Get-ChildItem $dir -ErrorAction SilentlyContinue | ForEach-Object {
        $skip = $false
        foreach ($p in $skipPatterns) { if ($_.Name -match $p) { $skip = $true; break } }
        if ($skip) { return }
        $prefix = if ($_.PSIsContainer) { "📁" } else { "📄" }
        $size = if (-not $_.PSIsContainer) { " ($( '{0:N0}' -f $_.Length) B)" } else { "" }
        $result += "  $prefix $($_.Name)$size"
    }
    return $result
}

function Get-RecentCommits($count=8) {
    $log = git log --oneline --no-decorate -$count 2>$null
    $result = @()
    if ($log) {
        foreach ($ln in $log) {
            if ($ln -match '^([a-f0-9]+)\s(.+)$') { $result += @{hash=$Matches[1]; msg=$Matches[2]} }
        }
    }
    return $result
}

function Get-ServiceName($containerName) {
    switch -Wildcard ($containerName) {
        "nodered*" { return "Node-RED" }
        "redis*" { return "Redis" }
        "sap-bridge*" { return "SAP Bridge" }
        "dify*" { return "Dify" }
        "mqtt*" { return "MQTT Broker" }
        "nginx-rescue*" { return "Nginx Rescue" }
        "sqlite-init*" { return "SQLite Init" }
        "docker-proxy*" { return "Docker Socket Proxy" }
        "watchdog*" { return "Watchdog" }
        "dashboard*" { return "Dashboard" }
        default { return $containerName }
    }
}

# ============================================================
# COLLECT DATA
# ============================================================

# Git info
$branch = git rev-parse --abbrev-ref HEAD 2>$null
$commits = Get-RecentCommits 10
$totalCommits = (git rev-list --count HEAD 2>$null)
$dirty = (git status --porcelain 2>$null)
$hasChanges = ($dirty -and $dirty.Trim() -ne "")

# File counts by type
$tsCount = Get-FileCountByExt $R ".ts"
$tsxCount = Get-FileCountByExt $R ".tsx"
$pyCount = Get-FileCountByExt $R ".py"
$jsCount = Get-FileCountByExt $R ".js"
$jsonCount = Get-FileCountByExt $R ".json"
$ymlCount_ = Get-FileCountByExt $R ".yml"
$yamlCount_ = Get-FileCountByExt $R ".yaml"
$mdCount = Get-FileCountByExt $R ".md"
$sqlCount = Get-FileCountByExt $R ".sql"
$ps1Count = Get-FileCountByExt $R ".ps1"
$shCount = Get-FileCountByExt $R ".sh"
$confCount = Get-FileCountByExt $R ".conf"

$totalFiles = $tsCount.count + $tsxCount.count + $pyCount.count + $jsCount.count + $jsonCount.count + $ymlCount_.count + $yamlCount_.count + $mdCount.count + $sqlCount.count + $ps1Count.count + $shCount.count + $confCount.count
$totalLines = $tsCount.lines + $tsxCount.lines + $pyCount.lines + $jsCount.lines + $jsonCount.lines + $ymlCount_.lines + $yamlCount_.lines + $mdCount.lines + $sqlCount.lines + $ps1Count.lines + $shCount.lines + $confCount.lines

# Docker compose services (hardcoded — YAML regex is fragile with comments)
$services = @(
    @{name="Node-RED"; container="robot-platform-nodered"; image="nodered/node-red:3.1.9"; ports="1880→1880"}
    @{name="Redis"; container="robot-platform-redis"; image="redis:7-alpine"; ports="6379→6379"}
    @{name="SAP Bridge"; container="robot-platform-sap-bridge"; image="python:3.11-slim"; ports="(内网)"}
    @{name="Dify"; container="robot-platform-dify"; image="langgenius/dify-api:latest"; ports="5001→5001"}
    @{name="MQTT Broker"; container="robot-platform-mqtt"; image="eclipse-mosquitto:2"; ports="1883→1883, 9001→9001 (WS)"}
    @{name="Nginx Rescue"; container="robot-platform-nginx-rescue"; image="nginx:alpine"; ports="8080→80"}
    @{name="SQLite Init"; container="robot-platform-sqlite-init"; image="nodered/node-red:3.1.9"; ports="(一次性)"}
    @{name="Docker Socket Proxy"; container="robot-platform-docker-proxy"; image="tecnativa/docker-socket-proxy"; ports="(内网)"}
    @{name="Watchdog"; container="robot-platform-watchdog"; image="robot-platform-watchdog:v3.4"; ports="9090→9090"}
    @{name="Dashboard"; container="robot-platform-dashboard"; image="robot-platform-dashboard:latest"; ports="4000→80"}
)

# Source file listing by directory
function Get-SourceTree($root, $dirs) {
    $result = @()
    foreach ($d in $dirs) {
        $fullPath = Join-Path $root $d
        if (Test-Path $fullPath) {
            $files = Get-ChildItem $fullPath -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
                $_.Extension -match '\.(ts|tsx|py|js|sql|json|yml|yaml|conf|ini|ps1|sh|bat|mdc|md)$' -and
                $_.FullName -notmatch 'node_modules|__pycache__|dist'
            } | Sort-Object FullName
            if ($files.Count -gt 0) {
                $result += @{dir=$d; files=$files}
            }
        }
    }
    return $result
}

$srcDirs1 = @("sap-bridge","watchdog","dashboard/src","nodered","scripts","sql","mqtt","redis","nginx","e2e","dify")
$srcTree = Get-SourceTree $R $srcDirs1

# (services hardcoded above)

# Parse init.sql for tables
$sqlPath = Join-Path $R "sql/init.sql"
$tables = @()
$tableName = ""; $cols = @(); $inTable = $false
if (Test-Path $sqlPath) {
    foreach ($ln in (Get-Content $sqlPath -Encoding UTF8)) {
        if ($ln -match '^CREATE TABLE IF NOT EXISTS (\w+)') {
            if ($inTable -and $tableName) {
                $tables += @{name=$tableName; columns=$cols -join ", "}
            }
            $tableName = $Matches[1]; $cols = @(); $inTable = $true
        } elseif ($inTable -and $ln -match '^\s+(\w+)\s+') {
            $cols += $Matches[1]
        } elseif ($ln -match '^\);') {
            if ($inTable -and $tableName) {
                $tables += @{name=$tableName; columns=$cols -join ", "}
            }
            $inTable = $false; $tableName = ""
        }
    }
}

# Detect triggers and indexes
$triggerCount = 0; $indexCount = 0
if (Test-Path $sqlPath) {
    $sqlContent = Get-Content $sqlPath -Encoding UTF8
    $triggerCount = ($sqlContent | Select-String "CREATE TRIGGER").Count
    $indexCount = ($sqlContent | Select-String "CREATE INDEX").Count
}

# Nodered flows
$flowsPath = Join-Path $R "nodered/flows.json"
$flowTabs = @()
if (Test-Path $flowsPath) {
    $flows = Get-Content $flowsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $seenTabs = @{}
    foreach ($node in $flows) {
        if ($node.type -eq "tab" -and $node.label -and -not $seenTabs.ContainsKey($node.id)) {
            $seenTabs[$node.id] = $true
            $flowTabs += @{label=$node.label; info=$node.info}
        }
    }
}

# Top-level directory listing
$topDirs = @(); $topFiles = @()
Get-ChildItem $R -ErrorAction SilentlyContinue | Sort-Object { $_.PSIsContainer -eq $false }, Name | ForEach-Object {
    $skipNames = @('node_modules','.git','dist','__pycache__')
    $skip = $false
    foreach ($sn in $skipNames) { if ($_.Name -eq $sn) { $skip = $true; break } }
    if ($skip) { return }
    if ($_.PSIsContainer) { $topDirs += @{name=$_.Name; count=(Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue).Count} }
    else { $topFiles += @{name=$_.Name; size=$_.Length} }
}

# Scripts listing
$scriptsDir = Join-Path $R "scripts"
$scripts = @()
if (Test-Path $scriptsDir) {
    $scripts = Get-ChildItem $scriptsDir -File -ErrorAction SilentlyContinue | Sort-Object Name
}

# E2E tests
$e2eDir = Join-Path $R "e2e"
$e2eCount = 0
if (Test-Path $e2eDir) {
    $e2eCount = (Get-ChildItem $e2eDir -Recurse -File -Filter "*.spec.*" -ErrorAction SilentlyContinue).Count
}

# ============================================================
# BUILD MARKDOWN OUTPUT
# ============================================================
$O = New-Object System.Collections.Generic.List[string]

$O.Add("# 代码库全景概览 — SAP-EWM 机器人调度平台")
$O.Add("")
$O.Add("> **生成日期：** $DF $TS")
$O.Add("> **项目版本：** v3.4")
$O.Add("> **根目录：** ``$R``")
$O.Add("> **Git 分支：** ``$branch``")
$O.Add("> **总提交数：** $totalCommits")
if ($hasChanges) { $O.Add("> **⚠️ 工作区有未提交变更**") }
$O.Add("")
$O.Add("---")
$O.Add("")

# --- SECTION 1: System Architecture ---
$O.Add("## 1. 系统架构")
$O.Add("")

$O.Add('```mermaid')
$O.Add('graph TB')
$O.Add('    subgraph "外部系统"')
$O.Add('        SAP[SAP EWM]')
$O.Add('        AGV[AGV 车队]')
$O.Add('        OPS[运维人员]')
$O.Add('    end')
$O.Add('')
$O.Add('    subgraph "Docker 内网"')
$O.Add('        NR[Node-RED<br/>Port 1880]')
$O.Add('        SB[SAP Bridge<br/>Port 8000]')
$O.Add('        D[Dashboard<br/>Port 4000]')
$O.Add('        MQ[MQTT Broker<br/>Port 1883/9001]')
$O.Add('        R[Redis<br/>Port 6379]')
$O.Add('        W[Watchdog<br/>Port 9090]')
$O.Add('        N[Nginx Rescue<br/>Port 8080]')
$O.Add('        DP[Docker Socket Proxy<br/>Port 2375]')
$O.Add('    end')
$O.Add('')
$O.Add('    SAP -->|OData/RFC| SB')
$O.Add('    SB -->|VDA5050| MQ')
$O.Add('    MQ -->|VDA5050| AGV')
$O.Add('    AGV -->|state/position| MQ')
$O.Add('    D -->|WS| MQ')
$O.Add('    D -->|REST| SB')
$O.Add('    OPS -->|HTTP| NR')
$O.Add('    OPS -->|HTTP| N')
$O.Add('    NR -->|HTTP| SB')
$O.Add('    W -->|Docker API| DP')
$O.Add('    W -.->|read| R')
$O.Add('    W -.->|alert| Feishu/WeCom')
$O.Add('```')
$O.Add("")

# --- SECTION 2: Docker Services ---
$O.Add("## 2. Docker 服务清单")
$O.Add("")
$O.Add("| # | 服务 | 容器名 | 镜像 | 端口（宿主机→容器） |")
$O.Add("|---|------|--------|------|---------------------|")
$i = 1
foreach ($svc in $services) {
    $img = $svc.image
    if ($img.Length -gt 45) { $img = $img.Substring(0,42)+"..." }
    $O.Add(("| {0} | **{1}** | ``{2}`` | {3} | {4} |" -f $i, $svc.name, $svc.container, $img, $svc.ports))
    $i++
}
$O.Add("")

# --- SECTION 3: Project Structure ---
$O.Add("## 3. 项目目录结构")
$O.Add("")
$O.Add("### 根目录")
$O.Add("")
$O.Add("| 类型 | 名称 | 说明 |")
$O.Add("|------|------|------|")
foreach ($td in $topDirs) {
    $desc = ""
    switch -Wildcard ($td.name) {
        "sap-bridge" { $desc = "Python FastAPI SAP EWM 集成服务" }
        "nodered" { $desc = "Node-RED 流程引擎配置与流定义" }
        "dashboard" { $desc = "React TS 运营监控面板" }
        "watchdog" { $desc = "Python 健康监控与自动熔断" }
        "mqtt" { $desc = "Mosquitto MQTT Broker 配置" }
        "redis" { $desc = "Redis 缓存配置" }
        "nginx" { $desc = "Nginx 急救面板配置" }
        "sql" { $desc = "数据库初始化脚本 + 迁移" }
        "scripts" { $desc = "辅助运维脚本（$($scripts.Count) 个）" }
        "e2e" { $desc = "Playwright E2E 测试（$e2eCount 个 spec）" }
        "dify" { $desc = "Dify LLM 翻译层配置" }
        "docs" { $desc = "项目文档" }
        "assets" { $desc = "静态资源" }
        "10_adr" { $desc = "架构决策记录" }
        "01_architecture" { $desc = "架构设计文档" }
        "02_deployment" { $desc = "部署文档" }
        "03_operations" { $desc = "运维手册" }
        "04_development" { $desc = "开发指南" }
        "06_meetings" { $desc = "会议记录" }
        "07_troubleshooting" { $desc = "故障排查指南" }
        "00_inbox" { $desc = "待处理文档" }
        ".claude" { $desc = "Claude Code 配置/规则/记忆" }
        ".cursor" { $desc = "Cursor IDE 配置/规则" }
        ".qoder" { $desc = "Qoder AI 技能缓存" }
        ".vscode" { $desc = "VS Code 工作区配置" }
        "fluent-bit" { $desc = "Fluent Bit 日志采集" }
        "gsd-tool" { $desc = "Get Shit Done CLI 工具" }
        "sap-ewm-mcp-servers" { $desc = "SAP EWM MCP 服务定义（子模块）" }
        "prompts" { $desc = "提示词模板" }
        "templates" { $desc = "文件模板" }
        "transcripts" { $desc = "会话记录" }
        default { $desc = "$($td.count) 个文件" }
    }
    $O.Add(("| 📁 | **{0}** | {1} |" -f $td.name, $desc))
}
foreach ($tf in $topFiles) {
    $desc = ""
    switch -Wildcard ($tf.name) {
        "docker-compose.yml" { $desc = "Docker 编排（10 服务）" }
        ".env" { $desc = "环境变量配置" }
        ".env.example" { $desc = "环境变量模板" }
        "package.json" { $desc = "NPM 依赖（Playwright 测试）" }
        "CLAUDE.md" { $desc = "AI 项目配置文件" }
        "SESSION_STATUS.md" { $desc = "会话状态跟踪" }
        "PROJECT_CONTEXT.md" { $desc = "项目上下文" }
        "PLAN.md" { $desc = "项目开发计划" }
        "README.md" { $desc = "项目说明" }
        "playwright.config.js" { $desc = "E2E 测试配置" }
        "crontab.example" { $desc = "定时任务模板" }
        default { $desc = "$('{0:N0}' -f $tf.size) B" }
    }
    $O.Add(("| 📄 | **{0}** | {1} |" -f $tf.name, $desc))
}
$O.Add("")

# --- SECTION 4: Source Code Analysis ---
$O.Add("## 4. 源码分布")
$O.Add("")
$O.Add("### 4.1 按语言统计")
$O.Add("")
$O.Add("| 语言 | 扩展名 | 文件数 | 代码行数 |")
$O.Add("|------|--------|--------|----------|")
$O.Add(("| TypeScript | .ts | {0} | {1:N0}" -f $tsCount.count, $tsCount.lines))
$O.Add(("| React TSX | .tsx | {0} | {1:N0}" -f $tsxCount.count, $tsxCount.lines))
$O.Add(("| Python | .py | {0} | {1:N0}" -f $pyCount.count, $pyCount.lines))
$O.Add(("| JavaScript | .js | {0} | {1:N0}" -f $jsCount.count, $jsCount.lines))
$O.Add(("| JSON | .json | {0} | {1:N0}" -f $jsonCount.count, $jsonCount.lines))
$O.Add(("| YAML | .yml/.yaml | {0} | {1:N0}" -f ($ymlCount_.count + $yamlCount_.count), ($ymlCount_.lines + $yamlCount_.lines)))
$O.Add(("| Markdown | .md | {0} | {1:N0}" -f $mdCount.count, $mdCount.lines))
$O.Add(("| SQL | .sql | {0} | {1:N0}" -f $sqlCount.count, $sqlCount.lines))
$O.Add(("| PowerShell | .ps1 | {0} | {1:N0}" -f $ps1Count.count, $ps1Count.lines))
$O.Add(("| Shell | .sh | {0} | {1:N0}" -f $shCount.count, $shCount.lines))
$O.Add(("| Config | .conf | {0} | {1:N0}" -f $confCount.count, $confCount.lines))
$O.Add(("| **合计** | | **{0:N0}** | **{1:N0}**" -f $totalFiles, $totalLines))
$O.Add("")

### 4.2 按模块分布
$O.Add("### 4.2 按模块分布")
$O.Add("")
$O.Add("| 模块 | 文件数 | 技术栈 | 职责 |")
$O.Add("|------|--------|--------|------|")

# Count files per module directory
$moduleDirs = @(
    @{path="sap-bridge"; name="SAP Bridge"; stack="Python FastAPI"},
    @{path="nodered"; name="Node-RED"; stack="JavaScript"},
    @{path="dashboard/src"; name="Dashboard"; stack="React TypeScript"},
    @{path="scripts"; name="脚本工具"; stack="PowerShell/Python/Bash"},
    @{path="e2e"; name="E2E 测试"; stack="Playwright"},
    @{path="watchdog"; name="Watchdog"; stack="Python"},
    @{path="sql"; name="数据库"; stack="SQL"},
    @{path="mqtt"; name="MQTT 配置"; stack="Config"},
    @{path="redis"; name="Redis 配置"; stack="Config"},
    @{path="nginx"; name="Nginx 配置"; stack="Config"},
    @{path="dify"; name="Dify 集成"; stack="Config"}
)
foreach ($md in $moduleDirs) {
    $mp = Join-Path $R $md.path
    $fc = 0
    if (Test-Path $mp) {
        $fc = (Get-ChildItem $mp -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'node_modules|__pycache__|dist' }).Count
    }
    $desc = ""
    switch ($md.name) {
        "SAP Bridge" { $desc = "OData/RFC 对接 SAP EWM, VDA5050 MQTT 发布, 心跳监控" }
        "Node-RED" { $desc = "订单编排, 状态机, 安全模式控制, 健康检查" }
        "Dashboard" { $desc = "运营监控 SPA, 3 个标签页, MQTT WebSocket 实时更新" }
        "脚本工具" { $desc = "备份, 日志清理, 简报生成, 技能审计" }
        "E2E 测试" { $desc = "跨浏览器测试, API 验证, 急救面板检测" }
        "Watchdog" { $desc = "容器监控, 三级熔断, 飞书/企微告警（1175 行）" }
        "数据库" { $desc = "SQLite 初始化: 7 表 + 2 触发器 + 5 索引" }
        "MQTT 配置" { $desc = "Mosquitto: 1883 MQTT + 9001 WebSocket" }
        "Redis 配置" { $desc = "256MB max, AOF+RDB, maxclients 100" }
        "Nginx 配置" { $desc = "离线急救面板, Node-RED 宕机时存活" }
        "Dify 集成" { $desc = "LLM 翻译层, 离线 HuggingFace 配置" }
    }
    $O.Add(("| **{0}** | {1} | {2} | {3} |" -f $md.name, $fc, $md.stack, $desc))
}
$O.Add("")

# --- SECTION 5: Database Schema ---
$O.Add("## 5. 数据库架构")
$O.Add("")
$O.Add("**存储引擎：** SQLite（WAL 模式）")
$O.Add("**位置：** ``/data/robot_platform.db``（Node-RED named volume）")
$O.Add("**表数量：** $($tables.Count)  |  触发器：$triggerCount  |  索引：$indexCount")
$O.Add("")

$O.Add("| 表名 | 字段 | 用途 |")
$O.Add("|------|------|------|")
foreach ($t in $tables) {
    $purpose = ""
    switch ($t.name) {
        "orders" { $purpose = "订单核心表（乐观锁 version, 状态流转）" }
        "outbox_events" { $purpose = "Outbox 模式（最终一致性, retry 机制）" }
        "audit_log" { $purpose = "审计日志（180天合规保护）" }
        "dead_letter_queue" { $purpose = "失败消息死信存储" }
        "zone_lock" { $purpose = "区域互斥锁（多品牌隔离）" }
        "robot_status" { $purpose = "机器人实时状态跟踪" }
        "api_deviation_log" { $purpose = "API 偏差记录（品牌固件差异）" }
        "dispatch_rules" { $purpose = "派单规则（灰度发布）" }
        default { $purpose = "" }
    }
    $colStr = $t.columns
    if ($colStr.Length -gt 80) { $colStr = $colStr.Substring(0,77)+"..." }
    $O.Add(("| **{0}** | {1} | {2} |" -f $t.name, $colStr, $purpose))
}
$O.Add("")

# --- SECTION 6: Node-RED Flows ---
$O.Add("## 6. Node-RED 流程")
$O.Add("")
$O.Add("**配置文件：** ``nodered/flows.json``（$( '{0:N0}' -f (Get-Item (Join-Path $R 'nodered/flows.json') -ErrorAction SilentlyContinue).Length ) B）")
$O.Add("")
foreach ($ft in $flowTabs) {
    $O.Add(("- **{0}** — {1}" -f $ft.label, $ft.info))
}
$O.Add("")

# --- SECTION 7: Key Configurations ---
$O.Add("## 7. 关键配置")
$O.Add("")
$O.Add("| 配置 | 路径 | 核心参数 |")
$O.Add("|------|------|----------|")
$O.Add("| 环境变量 | ``.env`` | SAP 连接, 通知通道, 多仓部署参数 |")
$O.Add("| Node-RED | ``nodered/settings.js`` | 认证, IP 白名单, Git Guard, Redis 存储, 审计日志 |")
$O.Add("| Redis | ``redis/redis.conf`` | 256MB maxmemory, AOF+RDB, maxclients 100 |")
$O.Add("| MQTT | ``mqtt/mosquitto.conf`` | 1883+9001(WS), 持久化, 匿名模式(开发) |")
$O.Add("| Watchdog | ``watchdog/config.yaml`` | CPU 70/80/95%, Checkpoint 3/5/10s, 告警冷却 |")
$O.Add("| Nginx Rescue | ``nginx/nginx.conf`` | 离线急救面板, Node-RED 宕机时存活 |")
$O.Add("| SAP Bridge | ``sap-bridge/sapnwrfc.ini`` | SAP NW RFC 连接模板 |")
$O.Add("| Docker Secrets | ``secrets/sap_password.txt`` | SAP 密码（不纳入 git） |")
$O.Add("")

# --- SECTION 8: API Endpoints ---
$O.Add("## 8. API 端点")
$O.Add("")
$O.Add("### 8.1 SAP Bridge（Python FastAPI）")
$O.Add("")
$O.Add("| 方法 | 路径 | 说明 |")
$O.Add("|------|------|------|")
$O.Add("| GET | ``/health`` | 健康检查（含 MQTT/Redis 连接状态） |")
$O.Add("| GET | ``/ready`` | 就绪检查（MQTT 断开返回 503） |")
$O.Add("| GET | ``/live`` | 存活检查（始终 200） |")
$O.Add("| GET | ``/api/v1/robots/status`` | 机器人连接状态（Redis） |")
$O.Add("| POST | ``/api/v1/orders`` | 创建 VDA5050 订单 → MQTT 发布 |")
$O.Add("| GET | ``/api/v1/orders`` | 订单列表（Redis） |")
$O.Add("")
$O.Add("### 8.2 Node-RED")
$O.Add("")
$O.Add("| 方法 | 路径 | 说明 |")
$O.Add("|------|------|------|")
$O.Add("| GET | ``/api/system-health`` | 系统健康状态 |")
$O.Add("| POST | ``/api/orders`` | 订单创建与派发 |")
$O.Add("| POST | ``/api/safe-mode`` | 进入安全模式 |")
$O.Add("| POST | ``/api/restore-mode`` | 退出安全模式 |")
$O.Add("| GET | ``/api/zone_lock`` | 区域锁查询 |")
$O.Add("")
$O.Add("### 8.3 Watchdog")
$O.Add("")
$O.Add("| 方法 | 路径 | 说明 |")
$O.Add("|------|------|------|")
$O.Add("| GET | ``/health`` | 健康状态 |")
$O.Add("| GET | ``/metrics`` | 指标采集 |")
$O.Add("| GET | ``/snapshots`` | 状态快照 |")
$O.Add("")

# --- SECTION 9: Git History ---
$O.Add("## 9. Git 提交历史")
$O.Add("")
$O.Add("**分支：** ``$branch``  |  **总提交：** $totalCommits")
if ($hasChanges) { $O.Add("**⚠️ 工作区有未提交的变更**") }
$O.Add("")
$O.Add("| Hash | 提交信息 |")
$O.Add("|------|----------|")
foreach ($c in $commits) {
    $msg = $c.msg
    if ($msg.Length -gt 70) { $msg = $msg.Substring(0,67)+"..." }
    $O.Add(("| ``{0}`` | {1} |" -f $c.hash, $msg))
}
$O.Add("")

# --- SECTION 10: Test Coverage ---
$O.Add("## 10. 测试覆盖")
$O.Add("")
$O.Add("| 类型 | 工具 | 数量 | 覆盖范围 |")
$O.Add("|------|------|------|----------|")
$O.Add(("| E2E | Playwright | {0} 个 spec | 多浏览器 (Chromium/Firefox/WebKit) + API + Auth + Rescue |" -f $e2eCount))
$O.Add("| 单元测试 | pytest | 4 个用例 | sap-bridge MQTT publisher |")
$O.Add("| 测试数据 | test-order.py | 1 个脚本 | 向 sap-bridge 发送测试订单 |")
$O.Add("")
$O.Add("**缺口：**")
$O.Add("- sap-bridge: 订单处理 API、心跳监控、Redis 状态管理均无测试")
$O.Add("- Dashboard: 无前端组件测试")
$O.Add("- Node-RED: 流程无自动化测试")
$O.Add("")

# --- SECTION 11: Alerting & Monitoring ---
$O.Add("## 11. 告警与监控")
$O.Add("")
$O.Add("**Watchdog 三级告警体系：**")
$O.Add("")
$O.Add("| 级别 | 条件 | 动作 |")
$O.Add("|------|------|------|")
$O.Add("| 🟢 正常 | CPU<70%, Checkpoint<3s | 无操作 |")
$O.Add("| 🟡 警告 | CPU>70% 或 Checkpoint>3s | 日志记录 |")
$O.Add("| 🟠 限流 | CPU>80% 或 Checkpoint>5s | 降低派单速率至 30% + 飞书告警 |")
$O.Add("| 🔴 安全模式 | CPU>95% 或 Redis OOM 或 3 次健康检查失败 | 停止派单 + 飞书 P0 告警 + 企微通知 |")
$O.Add("")
$O.Add("**告警通道：** 飞书机器人卡片（主） + 企业微信 Markdown（备） + 日志（Always）")
$O.Add("")

# --- SECTION 12: Current State & Gaps ---
$O.Add("## 12. 当前状态与待解决问题")
$O.Add("")
$O.Add("| 优先级 | 问题 | 影响 | 建议方案 |")
$O.Add("|--------|------|------|----------|")
$O.Add("| 🔴 | MQTT 匿名连接 | 安全风险，任意客户端可发布/订阅 | 启用密码认证 + ACL |")
$O.Add("| 🔴 | SAP Bridge 用 raw python 镜像 | 构建不可复现，体积 ~1GB | 启用 Dockerfile 编译 |")
$O.Add("| 🔴 | Outbox Tab 节点为空 | 最终一致性断链 | 补全 outbox 处理 flow |")
$O.Add("| 🟡 | sql/migrations/ 空 | 无法进行数据库版本演进 | 添加迁移脚本 |")
$O.Add("| 🟡 | dify 用 latest tag | 意外升级可能破坏兼容 | Pinned 版本号 |")
$O.Add("| 🟡 | sap-bridge 无持久存储 | 重启后订单丢失 | 接入 SQLite/Redis 持久化 |")
$O.Add("| 🟡 | 单元测试覆盖率低 | 回归风险 | 补充 pytest 用例 |")
$O.Add("| 🟢 | Dashboard 未接真实 MQTT | 运营看板仅展示静态 UI | 连接 docker-compose 内 MQTT |")
$O.Add("| 🟢 | 多品牌策略引擎未实现 | 无法同时管理不同品牌 AGV | v4.1 路线图 |")
$O.Add("| 🟢 | SQLite→PostgreSQL 未开始 | 水平扩展受限 | v4.0 路线图 |")
$O.Add("")

# --- SECTION 13: Version Roadmap ---
$O.Add("## 13. 版本路线图")
$O.Add("")
$O.Add("| 版本 | 里程碑 | 状态 | 内容 |")
$O.Add("|------|--------|------|------|")
$O.Add("| **v3.4** | 当前基线 | ✅ 已部署 | 10 容器 Docker Compose, Node-RED 编排, VDA5050 协议 |")
$O.Add("| **v3.5** | 生产加固 | ⏳ 待开始 | MQTT 认证, Dockerfile 编译, Outbox 补全, 测试补充 |")
$O.Add("| **v4.0** | 数据库迁移 | 📋 规划中 | SQLite → PostgreSQL, outbox 表迁移, DAO 层重构 |")
$O.Add("| **v4.1** | 策略引擎 | 📋 规划中 | TypeScript 策略模式, 多品牌适配器, Node-RED 集成 |")
$O.Add("| **v5.0** | K8s 编排 | 📋 规划中 | Kubernetes manifests, 水平扩展, 滚动更新 |")
$O.Add("")

# --- Footer ---
$O.Add("---")
$O.Add("")
$O.Add("*文档自动生成：$DF $TS | 生成脚本：``scripts\generate-codebase-overview.ps1``*")
$O.Add("*由 Claude Code 汇总分析*")
$O.Add("")

# ============================================================
# WRITE OUTPUT
# ============================================================
$nl = [System.Environment]::NewLine
[System.IO.File]::WriteAllText($outFile, ($O -join $nl), [System.Text.Encoding]::UTF8)

Pop-Location

Write-Output "✅ Codebase overview generated: $outFile"
