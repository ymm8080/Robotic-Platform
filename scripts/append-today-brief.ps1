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
    $n=[System.IO.Path]::GetFileName($p); $e=[System.IO.Path]::GetExtension($p).ToLower()
    if ($n -eq ".gitignore") { return "Git 忽略规则更新" }; if ($n -eq ".env.example") { return "环境变量模板更新" }
    if ($n -eq "package.json") { return "新增 playwright/dotenv 依赖和测试脚本" }
    if ($n -eq "docker-compose.yml") { return "服务编排与端口配置调整" }
    if ($n -eq "CLAUDE.md") { return "AI 项目配置同步至 v3.4" }
    if ($n -eq "playwright.config.js") { return "5 Project 测试框架配置" }
    if ($p -match 'sap-bridge/main\.py') { return "新增 health/ready/live 探针和机器人 API" }
    if ($p -match 'sap-bridge/mqtt_publisher') { return "VDA5050 MQTT 发布器（QoS 1 + LWT）" }
    if ($p -match 'sap-bridge/heartbeat') { return "Redis TTL 心跳监控" }
    if ($p -match 'sap-bridge/') { return "SAP Bridge 服务组件" }
    if ($p -match '\.claude/rules/|\.claude/skills/|\.claude/agents/') { return "AI 配置同步" }
    if ($p -match '\.cursor/rules/') { return "新增 VDA5050/SAP 专用规则" }
    if ($p -match '\.claude/settings\.json') { return "Hook 与记忆系统配置" }
    if ($p -match '\.claude/settings\.local') { return "本地权限豁免配置" }
    if ($p -match '\.claude/mcp\.json') { return "MCP 服务器注册" }
    if ($p -match '\.clinerules') { return "Claude Code 规则同步" }
    if ($p -match 'SESSION_STATUS') { return "项目状态追踪文件" }
    if ($p -match 'transcript-logger|load-transcript|update-session|append-today|show-session') { return "会话管理与简报脚本" }
    if ($p -match 'auto-daily-brief|today-session-context') { return "每日简报机制配置" }
    if ($p -match 'e2e/pages') { return "Page Object 封装" }
    if ($p -match 'e2e/fixtures') { return "5 个自定义 Fixture" }
    if ($p -match 'e2e/.*\.spec') { return "E2E 测试用例" }
    if ($p -match 'e2e/global') { return "测试全局钩子" }
    if ($p -match 'e2e/test-data') { return "测试数据" }
    if ($p -match 'docs/playwright') { return "测试框架文档" }
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
    if ($a -eq "CREATE") { return "新建文件" }
    if ($a -eq "DELETE") { return "清理废弃文件" }
    return "功能优化"
}
function gBrief($p) {
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

$areaOrder = @("A","B","C","D","E")

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











