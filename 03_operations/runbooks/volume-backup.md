# Volume Backup & Recovery Runbook

## Backup
Runs automatically daily at 02:00 via Windows Task Scheduler.
Can also be triggered manually:
```powershell
Start-ScheduledTask -TaskName SAP-EWM-Backup
# or directly:
bash scripts/backup-volumes.sh
```

## What Gets Backed Up
| Volume | Contents | Size (est.) |
|--------|----------|-------------|
| `nodered-data` | SQLite DB, Node-RED flows backup | ~10-100 MB |
| `redis-data` | Redis RDB + AOF | ~100 MB - 1 GB |
| `dify-data` | Dify model cache | ~1-3 GB |
| `mqtt-data` | Persistent MQTT messages | ~10-50 MB |
| `mqtt-logs` | Mosquitto logs | ~10-50 MB |
| `sap-bridge-logs` | SAP Bridge app logs | ~10-50 MB |
| `watchdog-logs` | Watchdog app logs | ~10-50 MB |
| `prometheus-data` | TSDB metrics (30d retention) | ~1-5 GB |
| `grafana-data` | Dashboard configs | ~10 MB |

## Recovery Steps

### Full Recovery
```powershell
# 1. Stop all services
docker compose down

# 2. Find the backup to restore
ls D:\EWM ROBOT\backups\

# 3. Restore each volume (replace YYYYMMDD_HHMMSS with actual backup timestamp)
$backup = "D:\EWM ROBOT\backups\YYYYMMDD_HHMMSS"
$volumes = @("nodered-data", "redis-data", "mqtt-data", "mqtt-logs", "sap-bridge-logs", "watchdog-logs")

foreach ($vol in $volumes) {
    docker run --rm -v ${vol}:/dest -v ${backup}:${backup} alpine:3.19 `
        tar xzf "${backup}/${vol}.tar.gz" -C /dest
    Write-Host "Restored ${vol} from ${backup}"
}

# 4. Start services
docker compose up -d
```

### Critical: Database-Only Recovery
```powershell
# Restore just the SQLite database
docker run --rm -v nodered-data:/dest -v D:\EWM ROBOT\backups\YYYYMMDD_HHMMSS:/backup alpine `
    tar xzf /backup/nodered-data.tar.gz -C /dest
docker compose restart nodered
```

## Retention
- Backups kept for **30 days**, auto-cleaned by scheduled task at 02:45
- Prometheus TSDB retains **30 days** of metrics (configured in prometheus.yml)
