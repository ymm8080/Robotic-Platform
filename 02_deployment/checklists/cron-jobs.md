# Scheduled Tasks / Cron Jobs v3.4

## Windows Task Scheduler

| Task Name | Schedule | Command | Description |
|-----------|----------|---------|-------------|
| SAP-EWM-Backup | Daily 02:00 | `bash scripts/backup-volumes.sh` | Volume backup |
| SAP-EWM-Backup-Cleanup | Daily 02:45 | `powershell Get-ChildItem ... \| Remove-Item` | Clean 30d+ backups |

Setup: Run `scripts/setup-backup-schedule.ps1` (as Administrator).

## Docker Container Schedules

| Schedule | Container | Mechanism | Description |
|----------|-----------|-----------|-------------|
| Every 30s | Watchdog | Internal polling loop | Health checks + circuit breaker |
| Every 30s | Node-RED (Outbox) | Inject node | Outbox event processing |
| Every 60s | SAP Bridge | Scheduler | Batch order collection from SAP |
| Every 5 min | SAP Bridge | Scheduler | Inventory sync from SAP |

## Verification

```powershell
# View scheduled tasks
Get-ScheduledTask -TaskName SAP-EWM-*

# Run backup immediately
Start-ScheduledTask -TaskName SAP-EWM-Backup

# Check last run time
Get-ScheduledTask -TaskName SAP-EWM-Backup | Get-ScheduledTaskInfo
```
