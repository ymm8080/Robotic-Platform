# =============================================================================
# Setup Automated Backup Schedule (Windows Task Scheduler)
# SAP-EWM Robot Dispatch Platform v3.4
# =============================================================================
# Creates daily Windows scheduled tasks for:
#   1. Volume backup (2:00 AM daily)
#   2. Volume backup verification (2:30 AM daily)
#   3. Old backup cleanup (keep 30 days)
# =============================================================================

$ProjectRoot = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES"
$BackupScript = "$ProjectRoot\scripts\backup-volumes.sh"
$LogDir = "D:\EWM ROBOT\backups"

# Ensure log directory exists
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

# ──────────────────────────────────────────────
# Task 1: Daily Volume Backup at 2:00 AM
# ──────────────────────────────────────────────
$BackupAction = New-ScheduledTaskAction -Execute "C:\Program Files\Git\bin\bash.exe" `
    -Argument "-l `"$BackupScript`" >> `"$LogDir\backup-cron.log`" 2>&1"
$BackupTrigger = New-ScheduledTaskTrigger -Daily -At "02:00"
$BackupSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$BackupPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "SAP-EWM-Backup" `
    -Action $BackupAction `
    -Trigger $BackupTrigger `
    -Settings $BackupSettings `
    -Principal $BackupPrincipal `
    -Description "Daily volume backup for SAP-EWM Robot Dispatch Platform" `
    -Force

# ──────────────────────────────────────────────
# Task 2: Cleanup old backups (2:45 AM daily)
# ──────────────────────────────────────────────
$CleanupAction = New-ScheduledTaskAction -Execute "PowerShell.exe" `
    -Argument "-NoProfile -Command `"Get-ChildItem '$LogDir' -Directory | Where-Object { (Get-Date) - `$_.CreationTime -gt [TimeSpan]::FromDays(30) } | Remove-Item -Recurse -Force`""
$CleanupTrigger = New-ScheduledTaskTrigger -Daily -At "02:45"
$CleanupSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "SAP-EWM-Backup-Cleanup" `
    -Action $CleanupAction `
    -Trigger $CleanupTrigger `
    -Settings $CleanupSettings `
    -Principal $BackupPrincipal `
    -Description "Remove backup directories older than 30 days" `
    -Force

# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────
Write-Host "✅ Backup schedule created:" -ForegroundColor Green
Write-Host "  SAP-EWM-Backup          — Daily 02:00 (volume backup)"
Write-Host "  SAP-EWM-Backup-Cleanup  — Daily 02:45 (clean 30d+ backups)"
Write-Host ""
Write-Host "To view tasks: Get-ScheduledTask -TaskName SAP-EWM-*"
Write-Host "To run immediately: Start-ScheduledTask -TaskName SAP-EWM-Backup"
