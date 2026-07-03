param()
# SessionStart: (1) reset stale context, (2) ensure today's brief exists
# Catches cases where the Stop hook failed or the session crashed

$R = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES"
$DS = (Get-Date).ToString("yyyyMMdd")
$DF = (Get-Date).ToString("yyyy-MM-dd")
$brDir = "D:\EWM ROBOT\daily-briefs"
$brFile = Join-Path $brDir "claude-code-today-brief-$DS.md"
$scriptPath = Join-Path $R "scripts\append-today-brief.ps1"
$ctxFile = Join-Path $R ".claude\today-session-context.json"

# Step 1: Reset today-session-context.json if stale
$needsReset = $true
if (Test-Path $ctxFile) {
    $ctx = $null
    try {
        $ctx = Get-Content $ctxFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Output "CORRUPT: Context file unreadable, will reset"
    }
    if ($ctx -and $ctx.date -eq $DS) {
        $needsReset = $false
        Write-Output "OK: Context is from today, keeping it"
    } elseif ($ctx) {
        Write-Output "STALE: Context date is '$($ctx.date)', resetting for $DF"
    }
}

if ($needsReset) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $template = @"
{
  "date": "$DS",
  "generated": "$ts",
  "phases": [],
  "files": {},
  "requests": [],
  "leftovers": [],
  "nextActions": []
}
"@
    Set-Content -Path $ctxFile -Value $template -Encoding UTF8
    Write-Output "RESET: Fresh context created for $DF"
}

# Step 2: Ensure today's brief exists
if (Test-Path $brFile) {
    Write-Output "OK: Daily brief already exists: $brFile"
    exit 0
}

Write-Output "MISSING: Daily brief for $DF, generating..."
$genCmd = "& '$scriptPath'"
powershell -ExecutionPolicy Bypass -Command $genCmd
if (Test-Path $brFile) {
    Write-Output "OK: Daily brief generated: $brFile"
} else {
    Write-Output "WARN: Script ran but no brief created (possibly no changes today)"
}
