param()
$R = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES"
$StatusFile = Join-Path $R "SESSION_STATUS.md"
$DateStr = (Get-Date).ToString("yyyy-MM-dd")
$TimeStr = (Get-Date).ToString("HH:mm:ss")
$CtxFile = Join-Path $R ".claude\today-session-context.json"

# Load context JSON for rich descriptions
$SC = $null; $HC = $false
if (Test-Path $CtxFile) {
    try { $SC = Get-Content $CtxFile -Raw -Encoding UTF8 | ConvertFrom-Json; $HC = $true } catch {}
}

Push-Location $R

# Get all of today's commits
$commits = git log --since="$DateStr 00:00" --format="%H|%ai|%s" --no-merges 2>$null
$sessionCommits = @()
if ($commits) {
    foreach ($line in $commits) {
        if ($line -match "^([a-f0-9]+)\|(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\|(.+)$") {
            $h = $Matches[1]; $dt = $Matches[2]; $msg = $Matches[3]
            $sessionCommits += @{ Hash = $h.Substring(0,7); Date = $dt; Message = $msg }
        }
    }
}

# File changes from git
$filesChanged = @()
if ($sessionCommits.Count -gt 0) {
    $lastH = $sessionCommits[0].Hash
    $firstH = $sessionCommits[$sessionCommits.Count - 1].Hash
    $diffs = git diff --name-status "${firstH}~1..${lastH}" 2>$null
    if ($diffs) {
        foreach ($ln in $diffs) {
            if ($ln -match "^([AMRDC])\s+(.+)$") {
                $code = $Matches[1]; $path = $Matches[2].Trim() -replace '\\', '/'
                $act = switch ($code) { "A" { "CREATE" } "M" { "MODIFY" } "R" { "REWRITE" } "D" { "DELETE" } default { "MODIFY" } }
                $filesChanged += @{ Path = $path; Action = $act }
            }
        }
    }
}

# Untracked files
$seen = @{}; foreach ($fc in $filesChanged) { $seen[$fc.Path] = $true }
$untracked = git ls-files --others --exclude-standard 2>$null
if ($untracked) {
    foreach ($u in ($untracked -split "`n")) {
        $u = $u.Trim() -replace '\\', '/'
        if ($u -and -not $seen.ContainsKey($u)) { $seen[$u] = $true; $filesChanged += @{ Path = $u; Action = "CREATE" } }
    }
}
Pop-Location

$timeRange = $TimeStr
if ($sessionCommits.Count -gt 0) {
    $firstD = $sessionCommits[$sessionCommits.Count - 1].Date
    $lastD = $sessionCommits[0].Date
    if ($firstD -match "\d{2}:\d{2}" -and $lastD -match "\d{2}:\d{2}") {
        $timeRange = "$($firstD.Substring(11,5))-$($lastD.Substring(11,5))"
    }
}

# Build markdown
$O = New-Object System.Collections.Generic.List[string]
$O.Add("# Project Session Status")
$O.Add("> Auto-generated. Updated at session end on $DateStr $TimeStr.")
$O.Add("")
$O.Add("## Current Phase")
$O.Add("Phase 3: Production Readiness (Week 7-8)")
$O.Add("")

if ($sessionCommits.Count -gt 0) {
    $O.Add("## Session ($DateStr $timeRange)")
    $O.Add("")
    $O.Add("### Commits ($($sessionCommits.Count))")
    $O.Add("")
    $O.Add("| # | Hash | Message |")
    $O.Add("|---|------|---------|")
    $i = 1
    foreach ($c in $sessionCommits) {
        $sm = if ($c.Message.Length -gt 80) { $c.Message.Substring(0,77)+"..." } else { $c.Message }
        $O.Add("| $i | $($c.Hash) | $sm |")
        $i++
    }
    $O.Add("")
}

# Completed items
$O.Add("### Completed This Session")
$O.Add("")
if ($HC -and $SC -and $SC.requests -and $SC.requests.Count -gt 0) {
    $i = 1
    foreach ($req in $SC.requests) {
        $d = if ($req.detail) { $req.detail } else { "" }
        $O.Add("$i. **$($req.title)** — $d")
        $O.Add("")
        $i++
    }
} elseif ($sessionCommits.Count -gt 0) {
    foreach ($c in $sessionCommits) { $O.Add("- $($c.Message)"); $O.Add("") }
} else {
    $O.Add("- (Session started, work in progress)"); $O.Add("")
}

# File changes
if ($filesChanged.Count -gt 0) {
    $O.Add("### File Changes ($($filesChanged.Count) files)")
    $O.Add("")
    $byA = @{}
    foreach ($fc in $filesChanged) {
        if (-not $byA.ContainsKey($fc.Action)) { $byA[$fc.Action] = New-Object System.Collections.ArrayList }
        [void]$byA[$fc.Action].Add($fc.Path)
    }
    foreach ($act in @("CREATE","MODIFY","REWRITE","DELETE")) {
        if (-not $byA.ContainsKey($act)) { continue }
        $paths = $byA[$act] | Sort-Object
        $lbl = switch ($act) { "CREATE" { "Created" } "MODIFY" { "Modified" } default { $act } }
        $O.Add("**$lbl ($($paths.Count)):**")
        foreach ($p in $paths) { $O.Add("- $p") }
        $O.Add("")
    }
}

# Key Decisions
$O.Add("### Key Decisions")
$O.Add("")
if ($HC -and $SC -and $SC.leftovers -and $SC.leftovers.Count -gt 0) {
    foreach ($lo in $SC.leftovers) { $O.Add("- $lo") }
} else {
    $O.Add("- (Tracked in git commit history)")
}
$O.Add("")

# Next Steps
$O.Add("### Next Steps (Priority Order)")
$O.Add("")
if ($HC -and $SC -and $SC.nextActions -and $SC.nextActions.Count -gt 0) {
    $i = 1; foreach ($na in $SC.nextActions) { $O.Add("$i. $na"); $i++ }
} else {
    $O.Add("1. Review this session's output for completion")
    $O.Add("2. Continue from Phase 3 execution plan")
}
$O.Add("")
$O.Add("---")
$O.Add("> Last updated: $DateStr $TimeStr")

$nl = [System.Environment]::NewLine
[System.IO.File]::WriteAllLines($StatusFile, $O, [System.Text.Encoding]::UTF8)
Write-Output "SESSION_STATUS.md updated: $($sessionCommits.Count) commits, $($filesChanged.Count) files"
