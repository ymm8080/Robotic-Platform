param()
$R = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES"
$DS = (Get-Date).ToString("yyyyMMdd"); $DF = (Get-Date).ToString("yyyy-MM-dd"); $TS = (Get-Date).ToString("HH:mm:ss")
$ctxFile = Join-Path $R ".claude\today-session-context.json"; $brDir = "D:\EWM ROBOT\daily-briefs"
if (-not (Test-Path $brDir)) { New-Item -ItemType Directory -Path $brDir -Force | Out-Null }
$brFile = Join-Path $brDir ("claude-code-today-brief-$DS.md")
$trDir = Join-Path $R "transcripts"; $trFile = Join-Path $trDir ("transcript-$DF.md")
$refDir = "D:\EWM ROBOT\REFERENCE"
$refSnapFile = Join-Path $R ".claude\reference-snapshot.json"

$SC=$null; $HC=$false
if (Test-Path $ctxFile) { try { $SC=(Get-Content $ctxFile -Raw -Encoding UTF8)|ConvertFrom-Json; $HC=$true } catch {} }

$FE=New-Object System.Collections.ArrayList; $seen=@{}; $ct=""
if (Test-Path $trFile) {
    foreach ($ln in (Get-Content $trFile -Encoding UTF8)) {
        if ($ln -match "^## (\d{2}:\d{2}:\d{2})$") { $ct=$Matches[1] }
        elseif ($ln -match "\[(CREATE|MODIFY)\] FILE: (.+)") {
            $p=$Matches[2].Trim() -replace '\\', '/'
            if (-not $seen.ContainsKey($p)) { $seen[$p]=$true; [void]$FE.Add((New-Object PSObject -Property @{T=$ct;P=$p;A=$Matches[1]})) }
        }
    }
}
Push-Location $R; $gd=git diff --name-status HEAD 2>$null
if ($gd) { foreach ($ln in $gd) { if ($ln -match "^([AMDR])\s+(.+)$") { $p=$Matches[2].Trim() -replace '\\', '/'; if (-not $seen.ContainsKey($p)) { $seen[$p]=$true; $code=$Matches[1]; if ($code -eq "A"){$a="CREATE"} elseif ($code -eq "M"){$a="MODIFY"} elseif ($code -eq "D"){$a="DELETE"} elseif ($code -eq "R"){$a="REWRITE"}else{$a="MODIFY"}; [void]$FE.Add((New-Object PSObject -Property @{T="";P=$p;A=$a})) } } } }
# Also capture untracked files (?? in git status) — git diff HEAD misses these entirely
$uf = git ls-files --others --exclude-standard 2>$null
if ($uf) { foreach ($u in ($uf -split "`n")) { $u=$u.Trim(); if ($u -and -not $seen.ContainsKey($u)) { $seen[$u]=$true; [void]$FE.Add((New-Object PSObject -Property @{T="";P=($u -replace '\\','/');A="CREATE"})) } } }
Pop-Location

# Filter: skip deleted files (check disk existence)
$sigFE=New-Object System.Collections.ArrayList; $trimmed=New-Object System.Collections.ArrayList
foreach ($fe in $FE) {
    $isTrivial = $fe.A -eq "DELETE" -or $fe.P -match '\.gitkeep|erl_crash\.dump|package-lock'
    # Files recorded as CREATE/MODIFY that no longer exist on disk were deleted by later operations — skip entirely
    if (-not $isTrivial -and $fe.A -ne "DELETE") {
        $resolved = if ([System.IO.Path]::IsPathRooted($fe.P)) { $fe.P } else { Join-Path $R $fe.P }
        if (-not (Test-Path $resolved)) { continue }
    }
    if ($isTrivial) { [void]$trimmed.Add($fe) } else { [void]$sigFE.Add($fe) }
}
$cnt=$sigFE.Count; $trivialCnt=$trimmed.Count

# === REFERENCE DIRECTORY CHANGE DETECTION ===
$refFE = New-Object System.Collections.ArrayList
$refChangedCnt = 0
$curSnap = @{}
if (Test-Path $refDir) {
    $oldSnap = @{}
    if (Test-Path $refSnapFile) {
        try {
            $snapData = Get-Content $refSnapFile -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($item in $snapData) { $oldSnap[$item.path] = @{ mtime=$item.mtime; size=$item.size } }
        } catch {}
    }
    $isFirstRun = ($oldSnap.Count -eq 0)
    Get-ChildItem $refDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $relPath = ($_.FullName.Substring($refDir.Length + 1) -replace '\\', '/')
        $curSnap[$relPath] = @{ mtime = $_.LastWriteTimeUtc.ToString('o'); size = $_.Length }
        if ($isFirstRun) { return }
        if (-not $oldSnap.ContainsKey($relPath)) {
            [void]$refFE.Add((New-Object PSObject -Property @{T=$TS;P="REFERENCE:$relPath";A="CREATE"}))
        } else {
            $old = $oldSnap[$relPath]
            if ($old.mtime -ne $curSnap[$relPath].mtime -or $old.size -ne $curSnap[$relPath].size) {
                [void]$refFE.Add((New-Object PSObject -Property @{T=$TS;P="REFERENCE:$relPath";A="MODIFY"}))
            }
        }
    }
    # Deletions
    foreach ($key in $oldSnap.Keys) {
        if (-not $curSnap.ContainsKey($key)) {
            [void]$refFE.Add((New-Object PSObject -Property @{T=$TS;P="REFERENCE:$key";A="DELETE"}))
        }
    }
    $refChangedCnt = $refFE.Count
    # Save REFERENCE snapshot immediately (even if no changes, to establish baseline)
    $snapArray = $curSnap.Keys | ForEach-Object { @{path=$_; mtime=$curSnap[$_].mtime; size=$curSnap[$_].size} }
    $snapArray | ConvertTo-Json | Set-Content $refSnapFile -Encoding UTF8
}
# Merge ref findings into sigFE
if ($refChangedCnt -gt 0) {
    foreach ($refFe in $refFE) { [void]$sigFE.Add($refFe) }
    $cnt = $sigFE.Count
}
if ($cnt -eq 0 -and $refChangedCnt -eq 0) { exit 0 }

# Helpers
function gDetail($p,$a) {
    # Cache for descriptions (avoid repeated file reads across area + phase grouping)
    if (-not $script:gDetailCache) { $script:gDetailCache = @{} }
    if ($script:gDetailCache.ContainsKey($p)) { return $script:gDetailCache[$p] }

    # Use context JSON for rich descriptions (detail + purpose + functions)
    if ($script:HC -and $script:SC -and $script:SC.files -and $script:SC.files.$p) {
        $fe = $script:SC.files.$p
        $parts = @()
        if ($fe.detail) { $parts += $fe.detail }
        if ($fe.purpose) { $parts += "目标: $($fe.purpose)" }
        if ($fe.functions -and $fe.functions.Count -gt 0) {
            $fnParts = @()
            foreach ($fn in $fe.functions) {
                $fnDesc = if ($fn.description) { "($($fn.description))" } else { "" }
                $fnParts += "$($fn.name)$fnDesc"
            }
            $parts += "fn: $($fnParts -join ', ')"
        }
        if ($parts.Count -gt 0) {
            $str = $parts -join " | "
            if ($str.Length -gt 300) { $str = $str.Substring(0,297)+"..." }
            $script:gDetailCache[$p] = $str; return $str
        }
    }
    # Content-aware description: read file content for meaningful summaries
    $fullPath = if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $R $p }
    try {
        if (Test-Path $fullPath) {
            $ext = [System.IO.Path]::GetExtension($p).ToLower()
            $fname = [System.IO.Path]::GetFileName($p)
            $desc = $null
            $isDockerfile = $fname -eq 'Dockerfile' -or $fname -like 'Dockerfile.*'
            if ($isDockerfile) {
                $lines = Get-Content $fullPath -Encoding UTF8 -TotalCount 10 -ErrorAction SilentlyContinue
                $cmts = @()
                foreach ($ln in $lines) {
                    $t = $ln.Trim()
                    if ($t -match '^#\s+(.+)') { $cmts += $Matches[1] }
                }
                if ($cmts.Count -gt 0) {
                    $cStr = (($cmts -join ' ') -replace '\s+', ' ').Trim()
                    if ($cStr.Length -gt 0) {
                        if ($cStr.Length -gt 200) { $cStr = $cStr.Substring(0,197) + '...' }
                        $desc = "Docker: $cStr"
                    }
                }
            } elseif ($ext) {
                switch ($ext) {
                    { $_ -in '.js','.jsx','.ts','.tsx' } {
                        $lines = Get-Content $fullPath -Encoding UTF8 -TotalCount 80 -ErrorAction SilentlyContinue
                        $inBlock = $false; $blockParts = @()
                        foreach ($ln in $lines) {
                            $t = $ln.Trim()
                            if ($t -match '^/\*\*') { $inBlock = $true; continue }
                            if ($inBlock) {
                                $clean = $t -replace '^\s*\*\s?', '' -replace '\*/$', ''
                                if ($clean.Length -gt 0) { $blockParts += $clean }
                                if ($t -match '\*/') { break }
                            }
                        }
                        if ($blockParts.Count -gt 0) {
                            $bStr = (($blockParts -join ' ') -replace '\s+', ' ').Trim()
                            if ($bStr.Length -gt 0) { $desc = "${ext}: $bStr" }
                        }
                        if (-not $desc) {
                            $topCmts = @()
                            foreach ($ln in $lines) {
                                $t = $ln.Trim()
                                if ($t -match '^//\s?(.+)') { $topCmts += $Matches[1] }
                                elseif ($t -and -not ($t -match '^//')) { break }
                            }
                            if ($topCmts.Count -gt 0) {
                                $cStr = (($topCmts -join ' ') -replace '\s+', ' ').Trim()
                                if ($cStr.Length -gt 0) { $desc = "${ext}: $cStr" }
                            }
                        }
                        if (-not $desc) {
                            $members = @()
                            foreach ($ln in $lines) {
                                if ($ln -match '^\s*export\s+(default\s+)?(function|class|const|let|var)\s+(\w+)') { $members += "导出:$($Matches[3])" }
                                elseif ($ln -match '^\s*(async\s+)?function\s+(\w+)') { $members += "函:$($Matches[2])()" }
                                elseif ($ln -match '^\s*class\s+(\w+)') { $members += "类:$($Matches[1])" }
                            }
                            if ($members.Count -gt 0) {
                                $mStr = ($members -join ', ')
                                if ($mStr.Length -gt 200) { $mStr = $mStr.Substring(0,197) + '...' }
                                $desc = "${ext}: $mStr"
                            }
                        }
                    }
                    '.py' {
                        $lines = Get-Content $fullPath -Encoding UTF8 -TotalCount 80 -ErrorAction SilentlyContinue
                        $inDoc = $false; $docParts = @()
                        foreach ($ln in $lines) {
                            $t = $ln.Trim()
                            if ($t -match '^"""') {
                                if (-not $inDoc) {
                                    $inDoc = $true
                                    $remain = $t -replace '^"""', ''
                                    if ($remain -and $remain -notmatch '^"""' -and $remain.Length -gt 0) { $docParts += $remain }
                                } else {
                                    $remain = $t -replace '"""$', ''
                                    if ($remain.Length -gt 0) { $docParts += $remain }
                                    break
                                }
                            } elseif ($inDoc) {
                                if ($t -match '"""') {
                                    $before = $t -replace '"""', ''
                                    if ($before.Length -gt 0) { $docParts += $before }
                                    break
                                }
                                $docParts += $t
                            }
                        }
                        if ($docParts.Count -gt 0) {
                            $docStr = (($docParts -join ' ') -replace '\s+', ' ').Trim()
                            if ($docStr.Length -gt 0) {
                                $desc = "Python: $docStr"
                            }
                        }
                        if (-not $desc) {
                            $members = @()
                            foreach ($ln in $lines) {
                                if ($ln -match '^\s*(async\s+)?def\s+(\w+)\s*\(') { $members += "函:$($Matches[2])()" }
                                if ($ln -match '^\s*class\s+(\w+)') { $members += "类:$($Matches[1])" }
                            }
                            if ($members.Count -gt 0) {
                                $mStr = ($members -join ', ')
                                if ($mStr.Length -gt 200) { $mStr = $mStr.Substring(0,197) + '...' }
                                $desc = "Python: $mStr"
                            }
                        }
                    }
                    '.json' {
                        $fi2 = $null; try { $fi2 = Get-Item $fullPath -ErrorAction Stop } catch {}
                        if ($fi2 -and $fi2.Length -le 1048576) {
                            $raw = Get-Content $fullPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
                            if ($raw) {
                                $json = $raw | ConvertFrom-Json -ErrorAction SilentlyContinue
                                $jParts = @()
                                if ($json -is [System.Array]) {
                                    $tabs = @(); $names = @()
                                    foreach ($node in ($json | Select-Object -First 200)) {
                                        if ($node.type -eq 'tab' -and $node.label) { $tabs += $node.label }
                                        elseif ($node.name) { $names += "$($node.type):$($node.name)" }
                                    }
                                    if ($tabs.Count -gt 0) { $jParts += "流: $($tabs -join ', ')" }
                                    if ($names.Count -gt 0 -and $jParts.Count -eq 0) {
                                        $nStr = $names | Select-Object -First 5
                                        $jParts += "节点: $($nStr -join ', ')"
                                    }
                                    if ($jParts.Count -eq 0) { $jParts += "数组($($json.Count)项)" }
                                } else {
                                    $props = @(); if ($json.PSObject.Properties) { $props = $json.PSObject.Properties.Name }
                                    if ($json.name) { $jParts += "名称: $($json.name)" }
                                    if ($json.description) { $jParts += "描述: $($json.description)" }
                                    if ($jParts.Count -eq 0 -and $props) {
                                        $pStr = $props | Select-Object -First 8
                                        $jParts += "键: $($pStr -join ', ')"
                                    }
                                }
                                if ($jParts.Count -gt 0) {
                                    $desc = "JSON: $($jParts -join '; ')"
                                }
                            }
                        }
                    }
                    { $_ -in '.yaml','.yml' } {
                        $lines = Get-Content $fullPath -Encoding UTF8 -TotalCount 30 -ErrorAction SilentlyContinue
                        $topKeys = @()
                        foreach ($ln in $lines) {
                            if ($ln -notmatch '^\s*#' -and $ln -match '^(\w[\w-]*)\s*:') { $topKeys += $Matches[1] }
                        }
                        if ($topKeys.Count -gt 0) {
                            $kStr = ($topKeys | Select-Object -First 10) -join ', '
                            if ($kStr.Length -gt 150) { $kStr = $kStr.Substring(0,147) + '...' }
                            $desc = "YAML: $kStr"
                        }
                    }
                    '.mdc' {
                        $lines = Get-Content $fullPath -Encoding UTF8 -TotalCount 20 -ErrorAction SilentlyContinue
                        $afterFm = $false
                        foreach ($ln in $lines) {
                            if ($ln.Trim() -eq '---' -and -not $afterFm) { $afterFm = $true; continue }
                            if ($ln.Trim() -eq '---' -and $afterFm) { $afterFm = $false; continue }
                            if ($ln -match '^\s*description:\s*(.+)$') {
                                $fmDesc = $Matches[1].Trim() -replace '^["'']|["'']$', ''
                                if ($fmDesc.Length -gt 0) { $desc = "规则: $fmDesc"; break }
                            }
                        }
                        if (-not $desc) {
                            $afterFm2 = $false
                            foreach ($ln in $lines) {
                                if ($ln.Trim() -eq '---' -and -not $afterFm2) { $afterFm2 = $true; continue }
                                if ($ln.Trim() -eq '---' -and $afterFm2) { $afterFm2 = $false; continue }
                                if ($afterFm2 -and $ln -notmatch '^\s*$') {
                                    $h = $ln.Trim() -replace '^#+\s*', ''
                                    if ($h.Length -gt 0) { $desc = "规则: $h"; break }
                                }
                            }
                        }
                    }
                    '.md' {
                        $lines = Get-Content $fullPath -Encoding UTF8 -TotalCount 20 -ErrorAction SilentlyContinue
                        foreach ($ln in $lines) {
                            if ($ln -match '^#\s+(.+)$') { $desc = "文档: $($Matches[1].Trim())"; break }
                            if ($ln -match '^##\s+(.+)$') { $desc = "文档: $($Matches[1].Trim())"; break }
                        }
                    }
                    { $_ -in '.ps1','.sh','.bat' } {
                        $lines = Get-Content $fullPath -Encoding UTF8 -TotalCount 10 -ErrorAction SilentlyContinue
                        $cmts = @()
                        foreach ($ln in $lines) {
                            $t = $ln.Trim()
                            if ($t -match '^#(.+)$') {
                                $c = $Matches[1].Trim()
                                if ($c -and $c -notmatch '^!') { $cmts += $c }
                            }
                        }
                        if ($cmts.Count -gt 0) {
                            $cStr = (($cmts -join ' ') -replace '\s+', ' ').Trim()
                            if ($cStr.Length -gt 0) {
                                if ($cStr.Length -gt 200) { $cStr = $cStr.Substring(0,197) + '...' }
                                $desc = "脚本: $cStr"
                            }
                        }
                    }
                }
            }
            if ($desc) {
                if ($desc.Length -gt 300) { $desc = $desc.Substring(0,297) + '...' }
                $script:gDetailCache[$p] = $desc
                return $desc
            }
        }
    } catch {
        # Silently fall through to pattern matching
    }
    # Fallback: path-based pattern matching with functional descriptions
    $n=[System.IO.Path]::GetFileName($p); $e=[System.IO.Path]::GetExtension($p).ToLower()
    if ($n -eq ".gitignore") { return "Git 忽略规则：排除 node_modules、secrets、.env 等" }
    if ($n -eq ".env.example") { return "环境变量模板：SAP/REDIS/MQTT 凭据占位符" }
    if ($n -eq "package.json") { return "NPM 依赖管理：playwright、dotenv 等" }
    if ($p -eq "docker-compose.yml") { return "Docker 编排：MQTT/Redis/Postgres/Node-RED 服务" }
    if ($n -eq "PLAN.md") { return "项目计划：10 阶段里程碑与任务分解" }
    if ($p -eq "CLAUDE.md") { return "AI 项目配置：v3.4 同步" }
    if ($p -eq ".clinerules") { return "Claude Code 规则同步" }
    if ($p -match 'sap-bridge/main\.py') { return "SAP EWM 集成：OData/RFC + 探针 health/ready/live + 机器人 API" }
    if ($p -match 'sap-bridge/mqtt_publisher') { return "VDA5050 MQTT 发布器：QoS 1 + LWT" }
    if ($p -match 'sap-bridge/heartbeat') { return "心跳监控：Redis TTL 过期检测" }
    if ($p -match 'sap-bridge/') { return "SAP Bridge 组件" }
    if ($p -match '\.claude/rules/000-global-iron-rules') { return "全局铁律：AI 行为底线" }
    if ($p -match '\.claude/rules/karpathy-guidelines') { return "Karpathy 指南：LLM 编码最佳实践" }
    if ($p -match '\.claude/rules/') { return "AI 规则：领域专用约束" }
    if ($p -match '\.claude/agents/') { return "AI 代理：专用子代理配置" }
    if ($p -match '\.claude/skills/') {
        $sn = $n -replace '\.md$',''
        $dn = [System.IO.Path]::GetFileName([System.IO.Path]::GetDirectoryName($p))
        switch -Wildcard ($sn) {
            "vda-5050-adapter-design" { return "VDA5050 适配器架构：多品牌机器人统一接口" }
            "event-driven-outbox" { return "Outbox 模式：发件箱持久化+死信队列" }
            "node-red-data-boundary" { return "Node-RED 数据边界：流隔离与类型约束" }
            "human-loop-notification-matrix" { return "人工通知矩阵：异常升级策略" }
            "compliance-checklist" { return "合规清单：物流行业标准" }
            "node-red-lowcode-patterns" { return "Node-RED 低代码：流模板与最佳实践" }
            "schema-migration-automation" { return "DB 迁移自动化：版本化管理" }
            "robot-firmware-ota" { return "机器人 OTA：远程固件升级" }
            "data-masking-gateway" { return "数据脱敏：坐标/订单脱敏" }
            "nodered-debug-interpretation" { return "Node-RED 调试：日志解析速查" }
            "physical-digital-friction" { return "物理-数字摩擦：传感器偏差补偿" }
            "language-boundary-contract" { return "跨语言契约：Python/JS 接口规范" }
            "robot-api-deviation-tracking" { return "API 偏差追踪：品牌固件差异" }
            "flow-integrity-check" { return "流程完整性：VDA5050 消息链路审计" }
            "llm-exception-noise-reduction" { return "LLM 降噪：AI 日志过滤" }
            "rescue-dashboard" { return "运维面板：离线监控+应急操作" }
            "docker-infra-patterns" { return "Docker 模式：容器化部署规范" }
            "notification-traffic-control" { return "通知流控：MQTT 限流+优先级" }
            "degradation-drill-sop" { return "降级演练 SOP：故障切换" }
            "cost-budget-sentinel" { return "成本哨兵：Token 消耗监控" }
            "implementation-roadmap" { return "实施路线图：阶段规划" }
            "nodered-git-workflow" { return "Node-RED Git：流文件版本管理" }
            default { return "$dn 技能：$sn" }
        }
    }
    if ($p -eq ".claude/settings.json") { return "Claude 配置：Hook、记忆、MCP" }
    if ($p -eq ".claude/settings.local") { return "本地权限豁免" }
    if ($p -eq ".claude/mcp.json") { return "MCP 注册：SAP Bridge/Dify/Node-RED" }
    if ($p -eq ".claude/reference-snapshot.json") { return "REFERENCE 快照：变更检测基线" }
    if ($p -match '\.claude/memory/') { return "记忆文件：跨会话项目知识" }
    if ($p -match 'scripts/append-today-brief') { return "简报脚本：git diff+context JSON → 中文工作简报" }
    if ($p -match 'scripts/') { return "辅助脚本" }
    if ($p -match 'sql/init\.sql') { return "PostgreSQL 初始化：outbox/状态/索引" }
    if ($p -match 'nodered/settings\.js') { return "Node-RED 配置：认证、存储、流路径" }
    if ($p -match 'nodered/flows\.json') { return "Node-RED 流：可视化编排逻辑" }
    if ($p -match 'watchdog/watchdog\.py') { return "健康监控：容器检查+自动恢复+告警" }
    if ($p -match 'dashboard/src/App\.tsx') { return "React 主应用：路由+状态管理" }
    if ($p -match 'dashboard/src/config\.ts') { return "Dashboard 配置：MQTT/API 端点" }
    if ($p -match 'dashboard/src/components/RobotCard') { return "机器人卡片：实时状态+位置+电池" }
    if ($p -match 'dashboard/src/components/RobotList') { return "机器人列表：多品牌概览" }
    if ($p -match 'dashboard/src/components/RobotDetail') { return "机器人详情：深度展示" }
    if ($p -match 'dashboard/src/components/TaskList') { return "任务列表：订单执行追踪" }
    if ($p -match 'dashboard/src/components/OrderForm') { return "订单表单：新任务创建" }
    if ($p -match 'dashboard/src/hooks/useMqtt') { return "MQTT Hook：实时订阅+状态同步" }
    if ($p -match 'dashboard/src/types/vda5050') { return "VDA5050 类型：消息接口+枚举" }
    if ($p -match 'dashboard/src/utils/format') { return "工具函数：坐标/时间格式化" }
    if ($p -match 'dashboard/Dockerfile') { return "Dashboard 构建：Nginx 静态托管" }
    if ($p -match 'dashboard/nginx\.default\.conf') { return "Nginx：SPA 路由+反向代理" }
    if ($p -match 'dashboard/') { return "Dashboard 组件" }
    if ($p -eq "dashboard/package.json") { return "Dashboard NPM 依赖" }
    if ($p -eq "dashboard/vite.config.ts") { return "Vite 构建配置" }
    if ($p -eq "dashboard/index.html") { return "Dashboard HTML 入口" }
    if ($p -eq "dashboard/tsconfig.json") { return "TypeScript 编译器配置" }
    if ($p -match 'mqtt/mosquitto\.conf') { return "MQTT Broker：1883+认证+ACL+持久化" }
    if ($p -match 'e2e/.*\.spec') { return "E2E 测试用例" }
    if ($p -match 'e2e/pages/') { return "Page Object 封装" }
    if ($p -match 'e2e/fixtures') { return "Fixture 夹具" }
    if ($p -match 'playwright\.config') { return "Playwright 测试框架配置" }
    if ($p -eq "crontab.example") { return "定时任务：健康检查+日志轮转" }
    if ($p -match 'dify/\.env') { return "Dify 环境：LLM Key+数据库连接" }
    if ($p -match '^REFERENCE:') {
        $rp = $p -replace '^REFERENCE:', ''
        if ($rp -match 'sap/') { return "SAP 参考文档" }
        if ($rp -match 'robots/') { return "机器人品牌参考" }
        if ($rp -match 'protocols/vda5050') { return "VDA5050 协议参考" }
        if ($rp -match 'protocols/') { return "通信协议参考" }
        if ($a -eq "CREATE") { return "新增参考文档" }
        if ($a -eq "DELETE") { return "删除参考文档" }
        return "参考文档更新"
    }
    # Enhanced fallback with file context (extension + directory)
    $ctxDir = [System.IO.Path]::GetDirectoryName($p)
    $ctxParts = @()
    if ($ctxDir -and $ctxDir.Trim('/') -ne '') {
        $segments = $ctxDir.Trim('/').Split('/') | Select-Object -First 2
        if ($segments) { $ctxParts += ($segments -join '/') }
    }
    if ($e -and $e -ne '') { $ctxParts += $e.TrimStart('.').ToUpper() }
    $ctxPrefix = if ($ctxParts.Count -gt 0) { "[$($ctxParts -join ' / ')] " } else { "" }
    if ($a -eq "CREATE") { $result = "${ctxPrefix}新建: $n" }
    elseif ($a -eq "DELETE") { $result = "${ctxPrefix}清理: $n" }
    else { $result = "${ctxPrefix}修改: $n" }
    if ($result.Length -gt 300) { $result = $result.Substring(0,297) + '...' }
    $script:gDetailCache[$p] = $result
    return $result
}
function gBrief($p) {
    # Context JSON first
    if ($script:HC -and $script:SC -and $script:SC.files -and $script:SC.files.$p -and $script:SC.files.$p.brief) { return $script:SC.files.$p.brief }
    if ($p -match '\.claude/rules/') { return "AI 规则" }; if ($p -match '\.claude/skills/') { return "AI 技能" }; if ($p -match '\.claude/agents/') { return "AI 代理" }
    if ($p -match '\.cursor/rules/') { return "Cursor 规则" }; if ($p -match 'e2e/pages/') { return "Page Object" }; if ($p -match 'e2e/spec') { return "E2E 测试" }
    if ($p -match 'e2e/fixtures') { return "Fixture" }; if ($p -match 'sap-bridge/') { return "SAP Bridge" }; if ($p -match 'scripts/') { return "脚本" }
    if ($p -match 'docs/') { return "文档" }; if ($p -match '\.claude/') { return "Claude 配置" }
    if ($p -match '^REFERENCE:') { $rp=$p -replace '^REFERENCE:',''; if($rp -match 'sap/'){return "SAP 参考"}elseif($rp -match 'robots/'){return "机器人参考"}elseif($rp -match 'protocols/'){return "协议参考"}else{return "参考文档"} }
    $e=[System.IO.Path]::GetExtension($p).ToLower()
    if ($e -eq '.md') { return "文档" }; if ($e -in '.json','.yml','.yaml') { return "配置" }; if ($e -eq '.js') { return "JS" }
    if ($e -eq '.py') { return "Python" }; if ($e -eq '.ps1') { return "PowerShell" }; if ($e -eq '.mdc') { return "AI 规则" }; return "文件"
}
function gIcon($a) { switch ($a) { "CREATE" { "🆕" } "REWRITE" { "🔄" } "MODIFY" { "✅" } "DELETE" { "❌" } default { "📄" } } }
function gLabel($a) { switch ($a) { "CREATE" { "新建" } "REWRITE" { "重写" } "MODIFY" { "修改" } "DELETE" { "删除" } default { $a } } }

# Map files to functional areas
function gArea($p) {
    if ($p -match '^docs/|^01_architecture|^05_reference|^03_operations|docker-compose|^\.env|^PLAN\.md|^\.claude/settings\.json|^\.gitignore|^sap-bridge/|^scripts/backup|^scripts/restore') { return @{K="A";N="项目规划与基础设施"} }
    if ($p -match '^\.claude/rules/|^\.claude/skills/|^\.claude/agents/|^\.cursor/rules/|^CLAUDE\.md|^\.clinerules|^\.claude/mcp\.json') { return @{K="B";N="Claude/Cursor 配置同步"} }
    if ($p -match '^e2e/|^playwright|^package\.json|^docs/playwright') { return @{K="C";N="测试框架搭建"} }
    if ($p -match '^\.claude/memory|^scripts/transcript|^scripts/update-session|^scripts/load-transcript|^scripts/append-today|^scripts/show-session|^\.claude/today-session|^\.claude/settings\.local|^SESSION_STATUS') { return @{K="D";N="记忆系统与开发流程"} }
    if ($p -match '^REFERENCE:') { return @{K="E";N="参考文档变更"} }
    return @{K="Z";N="其他"}
}

$areaOrder = @("A","B","C","D","E","Z")

# Build functional groups
$areaGroups = @{}
foreach ($fe in $sigFE) {
    $am = gArea $fe.P; $key = $am.K
    if (-not $areaGroups.ContainsKey($key)) { $areaGroups[$key]=@{N=$am.N;F=New-Object System.Collections.ArrayList} }
    $dt = gDetail $fe.P $fe.A; $tm = if ($fe.T){$fe.T}else{""}
    [void]$areaGroups[$key].F.Add(@{P=$fe.P;A=$fe.A;T=$tm;D=$dt})
}

# Build phase groups for detail tables
$planPhases=@(); $phaseGroups=@{}
function MapPhase($path) {
    if ($path -match '^\.claude/settings\.json') { return @{P="Phase 0";L="工作区加固";S="0.1 项目根配置"} }
    if ($path -match '^docs/|^01_architecture|^05_reference|^03_operations|^scripts/backup|^scripts/restore|^PLAN\.md|docker-compose|^\.env') { return @{P="Phase 1";L="核心稳定性";S="1.1 基础设施"} }
    if ($path -match '^sap-bridge/') { return @{P="Phase 1";L="核心稳定性";S="1.4 SAP Bridge"} }
    if ($path -match '^\.claude/rules/|^\.claude/skills/|^\.claude/agents/|^\.cursor/rules/') { return @{P="Phase 4";L="持续优化";S="4.2 AI 配置同步"} }
    if ($path -match '^CLAUDE\.md|^\.clinerules|^\.claude/mcp|^\.claude/settings') { return @{P="Phase 4";L="持续优化";S="4.1 Claude 配置"} }
    if ($path -match '^e2e/|^playwright|^package\.json') { return @{P="Phase 3";L="生产就绪";S="3.1 测试框架"} }
    if ($path -match '^\.claude/memory|^scripts/transcript|^scripts/update-session|^scripts/load-transcript|^scripts/append-today|^\.claude/today-session|^SESSION_STATUS|^\.claude/settings\.local') { return @{P="Phase 4";L="持续优化";S="4.1 记忆与开发流程"} }
    if ($path -match '^REFERENCE:') { return @{P="Phase R";L="参考文档";S="R.1 外部参考"} }
    return @{P="Phase 4";L="持续优化";S="4.x 其他"}
}
foreach ($fe in $sigFE) {
    # Skip REFERENCE entries — handled in dedicated section
    if ($fe.P -match '^REFERENCE:') { continue }
    $pm=MapPhase $fe.P; $key="{0}|{1}|{2}" -f $pm.P,$pm.L,$pm.S
    if (-not $phaseGroups.ContainsKey($key)) { $phaseGroups[$key]=New-Object System.Collections.ArrayList; $planPhases+=@{P=$pm.P;L=$pm.L;S=$pm.S;K=$key} }
    $dt=gDetail $fe.P $fe.A; $br=gBrief $fe.P; $tm=if ($fe.T){$fe.T}else{""}
    [void]$phaseGroups[$key].Add(@{P=$fe.P;A=$fe.A;T=$tm;B=$br;D=$dt})
}
$seenK=@{}; $uniq=@()
foreach ($pp in $planPhases) { if (-not $seenK.ContainsKey($pp.K)) { $seenK[$pp.K]=$true; $uniq+=$pp } }
$order=@{"Phase 0"=0;"Phase 1"=1;"Phase 2"=2;"Phase 3"=3;"Phase 4"=4}
$uniq=$uniq | Sort-Object { $order[$_.P] }

# Build markdown
$O=New-Object System.Collections.Generic.List[string]

$O.Add("# Claude Code 今日工作简报"); $O.Add("")
$O.Add(("> **日期：** {0}" -f $DF)); $O.Add(("> **项目：** SAP-EWM 机器人调度平台 v3.4")); $O.Add(("> **根目录：** ``{0}``" -f $R)); $O.Add(("> **总文件数：** {0} 个（新建 + 修改）" -f ($cnt+$trivialCnt))); $O.Add("")
$O.Add("---"); $O.Add("")

# Compute global time range from all entries with timestamps
$globalTimes=@(); foreach ($fe in $FE) { if ($fe.T -and $fe.T -ne "") { $globalTimes+=$fe.T } }
$globalTimeRange = "—"
if ($globalTimes.Count -gt 0) {
    $sortedT = $globalTimes | Sort-Object
    $globalTimeRange = "{0}-{1}" -f $sortedT[0], $sortedT[-1]
} else {
    $globalTimeRange = $TS
}

# Overview: functional summary with file lists and time range
$O.Add("## 今日工作总览"); $O.Add("")
$O.Add("| 时间 | 功能领域 | 主要变更 | 文件数 |"); $O.Add("|------|----------|----------|--------|")
foreach ($ak in $areaOrder) {
    if (-not $areaGroups.ContainsKey($ak)) { continue }
    $ag = $areaGroups[$ak]; $fc = $ag.F.Count
    # Collect time range (use global fallback if no per-area timestamps)
    $times=@(); foreach ($ff in $ag.F) { if ($ff.T) { $times+=$ff.T } }
    $timeRange = $globalTimeRange
    if ($times.Count -gt 0) {
        $sorted2 = $times | Sort-Object
        $timeRange = "{0}-{1}" -f $sorted2[0], $sorted2[-1]
    }
    # Collect unique file names
    $fileNames=@{}; $fileBriefs=@{}
    foreach ($ff in $ag.F) {
        $fname = [System.IO.Path]::GetFileName($ff.P)
        if (-not $fileNames.ContainsKey($fname)) { $fileNames[$fname]=$true; $fileBriefs[$fname]=$ff.D }
    }
    $nameList = @(); $count=0
    foreach ($fn in $fileNames.Keys) {
        $br = $fileBriefs[$fn]
        if ($br.Length -gt 25) { $br = $br.Substring(0,22)+"..." }
        $nameList += ("{0}" -f $fn)
        $count++
    }
    $summary = $ag.N
    if ($nameList.Count -gt 0) {
        $fileStr = $nameList -join "、"
        if ($fileStr.Length -gt 80) { $fileStr = $fileStr.Substring(0,77)+"..." }
        $summary += "（{0}）" -f $fileStr
    }
    $O.Add(("| {0} | **{1}** | {2} | {3} |" -f $timeRange, $ag.N, $summary, $fc))
}
if ($trivialCnt -gt 0) { $O.Add(("| — | 清理维护 | 删除废弃/冗余文件 | {0} |" -f $trivialCnt)) }
$O.Add(("| **合计** | — | **{0}** |" -f ($cnt+$trivialCnt)))
$O.Add(""); $O.Add("---"); $O.Add("")

# Change summary by PLAN.md phase
$O.Add("## 各阶段变更概要"); $O.Add("")
$phaseDesc = @{"Phase 0"="工作区加固：项目根配置、文档基线、卫生清理"; "Phase 1"="核心稳定性：基础设施加固、备份恢复、SAP Bridge、密钥审计"; "Phase 2"="功能完整性：多品牌策略、订单管理、SAP 深度集成、Dashboard"; "Phase 3"="生产就绪：测试框架、CI/CD、监控与可观测性"; "Phase 4"="持续优化：AI 配置同步、记忆系统、开发脚本"}
$prevPhase = ""
foreach ($pp in $uniq) {
    $files=$phaseGroups[$pp.K]; $fc=$files.Count
    if ($pp.P -ne $prevPhase) {
        $prevPhase = $pp.P
        $desc = if ($phaseDesc.ContainsKey($pp.P)) { $phaseDesc[$pp.P] } else { "" }
        if ($desc) { $O.Add(("**{0}**：{1}" -f $pp.P, $desc)) }
    }
    $briefSet=@{}; foreach ($ff in $files) { $briefSet[$ff.D]=$true }; $briefArr=@(); foreach ($bd in $briefSet.Keys) { $briefArr+=$bd }
    $brief = $briefArr -join "；"
    if ($brief.Length -gt 100) { $brief = $brief.Substring(0,97)+"..." }
    $O.Add(("  - {0}（{1} 文件）：{2}" -f $pp.S, $fc, $brief))
}
$O.Add("")
$O.Add("---"); $O.Add("")

# Phase detail sections
$curP=""
foreach ($pp in $uniq) {
    $files=$phaseGroups[$pp.K]
    if ($pp.P -ne $curP) { $curP=$pp.P; $O.Add(("## {0} — {1}" -f $pp.P, $pp.L)); $O.Add("") }
    $O.Add(("### {0}" -f $pp.S)); $O.Add("")
    $O.Add("| 时间 | 文件路径 | 类型 | 说明 |"); $O.Add("|------|----------|------|------|")
    foreach ($ff in $files) {
        $tm=if ($ff.T){$ff.T}else{"—"}; $icon=gIcon $ff.A; $label=gLabel $ff.A; $desc=$ff.D
        $O.Add(("| {0} | ``{1}`` | {2} {3} | {4} |" -f $tm, $ff.P, $icon, $label, $desc))
    }
    $O.Add("")
}

# Reference document changes
if ($refChangedCnt -gt 0) {
    $O.Add("## 参考文档变更"); $O.Add("")
    $O.Add("| 时间 | 文件路径 | 类型 | 说明 |"); $O.Add("|------|----------|------|------|")
    foreach ($refFe in $refFE) {
        $displayPath = $refFe.P -replace '^REFERENCE:', ''
        $tm=if ($refFe.T){$refFe.T}else{"—"}; $icon=gIcon $refFe.A; $label=gLabel $refFe.A
        $desc = "参考文档"
        if ($displayPath -match 'sap/') { $desc = "SAP 参考" }
        elseif ($displayPath -match 'robots/') { $desc = "机器人参考" }
        elseif ($displayPath -match 'protocols/vda5050') { $desc = "VDA5050 协议" }
        elseif ($displayPath -match 'protocols/') { $desc = "通信协议" }
        $O.Add(("| {0} | ``{1}`` | {2} {3} | {4} |" -f $tm, $displayPath, $icon, $label, $desc))
    }
    $O.Add("")
}

# Trivial changes (if any)
if ($trivialCnt -gt 0) {
    $O.Add("## 清理维护"); $O.Add("")
    $O.Add("| 时间 | 文件路径 | 操作 | 说明 |"); $O.Add("|------|----------|------|------|")
    foreach ($fe in $trimmed) {
        $tm2=if ($fe.T){$fe.T}else{"—"}; $icon2=gIcon $fe.A; $label2=gLabel $fe.A
        $O.Add(("| {0} | ``{1}`` | {2} {3} | 清理废弃文件 |" -f $tm2, $fe.P, $icon2, $label2))
    }
    $O.Add("")
}

# Key files
$O.Add("## 关键文件速查"); $O.Add(""); $O.Add("| 用途 | 路径 |"); $O.Add("|------|------|")
$kf=@{"开发总计划"="PLAN.md";"AI 项目配置"="CLAUDE.md";"AI 规则目录"=".claude/rules/";"Claude 项目设置"=".claude/settings.json"}
foreach ($kv2 in $kf.Keys) { $O.Add(("| {0} | ``{1}`` |" -f $kv2, $kf[$kv2])) }; $O.Add("")

# Tooling changes summary (from today-session-context.json requests)
if ($script:HC -and $script:SC -and $script:SC.requests -and $script:SC.requests.Count -gt 0) {
    $O.Add("## 工具变更摘要"); $O.Add("")
    $O.Add("| 变更 | 说明 |"); $O.Add("|------|------|")
    foreach ($req in $script:SC.requests) {
        $t = $req.title
        $d = if ($req.detail) { $req.detail.Substring(0, [Math]::Min($req.detail.Length, 200)) } else { "" }
        if ($d.Length -ge 200) { $d += "..." }
        $O.Add(("| {0} | {1} |" -f $t, $d))
    }
    $O.Add("")
}

# Next actions - intelligent from PLAN.md + project state (always generated)
$O.Add("## 后续行动"); $O.Add("")

$naList=New-Object System.Collections.ArrayList

# Check actual project state (filesystem checks)
$hasDotEnv = Test-Path (Join-Path $R ".env")
$hasSecrets = Test-Path (Join-Path $R "secrets\sap_password.txt")
$hasCIDeploy = Test-Path (Join-Path $R ".github\workflows")
try { $hasNodeModulesGitignored = Select-String "node_modules" (Join-Path $R ".gitignore") -SimpleMatch -Quiet } catch { $hasNodeModulesGitignored = $false }
try { $hasADRs = (Get-ChildItem (Join-Path $R "10_adr") -Filter "*.md" -ErrorAction Stop).Count -gt 0 } catch { $hasADRs = $false }
$hasStrategyDir = Test-Path (Join-Path $R "sap-bridge\strategies")
$hasNginxSW = Test-Path (Join-Path $R "nginx\sw.js")

# Phase 0 remaining — workspace hardening
if (-not $hasDotEnv) { [void]$naList.Add("【Phase 0】创建 .env 文件（从 .env.example 复制），配置 SAP/REDIS/MQTT 凭据") }
if (-not $hasSecrets) { [void]$naList.Add("【Phase 0】创建 secrets/sap_password.txt 并加入 .gitignore，完善密钥管理") }
if (-not $hasNodeModulesGitignored) { [void]$naList.Add("【Phase 0】将 node_modules/ 加入 .gitignore，清理版本跟踪") }

# Phase 1 remaining — core stability
[void]$naList.Add("【Phase 1】验证 SAP Bridge OData 连接：curl http://localhost:1880/sap-bridge/health")
[void]$naList.Add("【Phase 1】配置 Redis TTL 策略：所有 SET 确保带 EXPIRE，防止内存泄漏")
[void]$naList.Add("【Phase 1】实施 MQTT QoS 1 + 序列号审计，验证发布器配置")
[void]$naList.Add("【Phase 1】配置 Watchdog 告警阈值：CPU >80%、Redis >75%、错误率 >5%")

# Phase 2 remaining — feature completeness (next major milestone)
if (-not $hasStrategyDir) {
    [void]$naList.Add("【Phase 2】搭建机器人品牌策略框架：创建 strategy.ts 接口与品牌注册表")
    [void]$naList.Add("【Phase 2】开发订单管理服务：Redis 优先级队列 + outbox 持久化")
}
[void]$naList.Add("【Phase 2】实现 SAP EWM 深度集成：OData CRUD、库存同步、IDoc 监听")
[void]$naList.Add("【Phase 2】优化 Rescue Dashboard：离线架构、实时位置、E-Stop、电池概览")

# Phase 3 remaining — production readiness
[void]$naList.Add("【Phase 3】运行 Playwright 测试套件：npm run test:e2e，确认 63 用例通过")
if (-not $hasCIDeploy) { [void]$naList.Add("【Phase 3】配置 CI/CD 流水线：GitHub Actions → lint → test → build") }
[void]$naList.Add("【Phase 3】配置 Prometheus + Grafana 监控大盘")
if (-not $hasNginxSW) { [void]$naList.Add("【Phase 3】实现 Nginx Rescue Dashboard 离线 Service Worker") }

# Phase 4 remaining — continuous
if (-not $hasADRs) { [void]$naList.Add("【Phase 4】编写 ADR 记录关键架构决策（策略模式、订单设计）") }
[void]$naList.Add("【Phase 4】执行 git commit 提交变更并推送")

# Always
[void]$naList.Add("更新 SESSION_STATUS.md 记录当前阶段与完成项")

$i=1; foreach ($item in $naList) { $O.Add(("{0}. {1}" -f $i, $item)); $i++ }
$O.Add("")

$O.Add("---"); $O.Add(""); $O.Add(("*文档生成：{0} {1} | 由 Claude Code 自动汇总*" -f $DF, $TS)); $O.Add("")

$nl=[System.Environment]::NewLine; [System.IO.File]::WriteAllText($brFile, ($O -join $nl), [System.Text.Encoding]::UTF8)











