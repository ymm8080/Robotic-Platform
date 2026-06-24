#!/bin/bash
# =============================================================================
# Volume Backup Script — SAP-EWM Robot Dispatch Platform
# Backup all named Docker volumes to a timestamped directory.
# =============================================================================
set -euo pipefail

BACKUP_BASE="${BACKUP_DIR:-D:/EWM ROBOT/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"
VOLUMES="nodered-data redis-data dify-data mqtt-data mqtt-logs sap-bridge-logs watchdog-logs prometheus-data grafana-data"
COMPOSE_FILE="D:/EWM ROBOT/ROBOTIC PLATFORM CODES/docker-compose.yml"
LOG_FILE="${BACKUP_DIR}/backup.log"

mkdir -p "${BACKUP_DIR}"

echo "[$(date +%H:%M:%S)] Starting volume backup..." | tee -a "${LOG_FILE}"
echo "  Backup dir: ${BACKUP_DIR}" | tee -a "${LOG_FILE}"

# Stop services to ensure data consistency (optional: set SKIP_STOP=1 for hot backup)
if [ "${SKIP_STOP:-0}" != "1" ]; then
  echo "[$(date +%H:%M:%S)] Stopping services..." | tee -a "${LOG_FILE}"
  docker compose -f "${COMPOSE_FILE}" stop
fi

for vol in $VOLUMES; do
  echo "[$(date +%H:%M:%S)] Backing up ${vol}..." | tee -a "${LOG_FILE}"
  docker run --rm \
    -v "${vol}:/source:ro" \
    -v "${BACKUP_DIR}:/backup" \
    alpine:3.19 \
    tar czf "/backup/${vol}.tar.gz" -C /source .
  echo "  → ${BACKUP_DIR}/${vol}.tar.gz ($(du -h "${BACKUP_DIR}/${vol}.tar.gz" | cut -f1))" | tee -a "${LOG_FILE}"
done

# Restart services
if [ "${SKIP_STOP:-0}" != "1" ]; then
  echo "[$(date +%H:%M:%S)] Restarting services..." | tee -a "${LOG_FILE}"
  docker compose -f "${COMPOSE_FILE}" start
fi

# Create manifest
cat > "${BACKUP_DIR}/MANIFEST.txt" <<EOF
Backup Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Host: $(hostname 2>/dev/null || echo "unknown")
Docker Version: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
Compose File: ${COMPOSE_FILE}
Volumes: ${VOLUMES}
Notes: Hot backup = ${SKIP_STOP:-0}
EOF

echo "[$(date +%H:%M:%S)] Backup complete → ${BACKUP_DIR}" | tee -a "${LOG_FILE}"
echo ""
echo "Summary:"
ls -lh "${BACKUP_DIR}"/*.tar.gz 2>/dev/null | awk '{print "  " $NF " (" $5 ")"}'
