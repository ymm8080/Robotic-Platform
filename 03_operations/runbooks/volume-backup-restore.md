# Volume Backup & Restore Runbook

**Last Updated**: 2026-06-21

## Backup

### Manual backup
```bash
cd "D:/EWM ROBOT/ROBOTIC PLATFORM CODES/"
bash scripts/backup-volumes.sh
```

### Hot backup (without stopping services)
```bash
SKIP_STOP=1 bash scripts/backup-volumes.sh
```

### Scheduled backup (via cron / Windows Task Scheduler)
```powershell
# Windows Task Scheduler action:
powershell -Command "bash D:/EWM\ ROBOT/ROBOTIC\ PLATFORM\ CODES/scripts/backup-volumes.sh"
```
**Schedule**: Daily at 02:00 UTC

## Restore

### List available backups
```bash
ls -d "D:/EWM ROBOT/backups/"*/
```

### Full restore
```bash
bash scripts/restore-volumes.sh "D:/EWM ROBOT/backups/20260621_143000"
```

### Single volume restore (manual)
```bash
# Restore just Redis data
docker run --rm \
  -v redis-data:/target \
  -v "D:/EWM ROBOT/backups/20260621_143000:/backup:ro" \
  alpine:3.19 \
  tar xzf "/backup/redis-data.tar.gz" -C /target
```

## Verification

After restore:
```bash
docker compose ps                    # All services running
docker exec robot-platform-redis redis-cli PING  # Redis data intact
curl http://localhost:1880/api/system-health     # Node-RED healthy
```

## Retention

- Daily backups: 7 days
- Weekly backups: 1 month
- Monthly backups: 1 year
- Cleanup: `find D:/EWM\ ROBOT/backups/ -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +`
