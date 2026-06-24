#!/bin/bash
# =============================================================================
# Volume Restore Script — SAP-EWM Robot Dispatch Platform
# Restore all named Docker volumes from a timestamped backup directory.
# Usage: bash scripts/restore-volumes.sh <backup-timestamp-or-path>
# Example: bash scripts/restore-volumes.sh 20260624_135945
# =============================================================================
set -euo pipefail

BACKUP_BASE="${BACKUP_DIR:-D:/EWM ROBOT/backups}"
TIMESTAMP="${1:-}"
COMPOSE_FILE="D:/EWM ROBOT/ROBOTIC PLATFORM CODES/docker-compose.yml"

if [ -z "${TIMESTAMP}" ]; then
    echo "Usage: bash scripts/restore-volumes.sh <timestamp>"
    echo ""
    echo "Available backups:"
    ls -1 "${BACKUP_BASE}" 2>/dev/null || echo "  (none in ${BACKUP_BASE})"
    exit 1
fi

if [ -d "${TIMESTAMP}" ]; then
    RESTORE_DIR="${TIMESTAMP}"
else
    RESTORE_DIR="${BACKUP_BASE}/${TIMESTAMP}"
fi

if [ ! -d "${RESTORE_DIR}" ]; then
    echo "Backup not found: ${RESTORE_DIR}"
    ls -1 "${BACKUP_BASE}" 2>/dev/null
    exit 1
fi

VOLUMES="nodered-data redis-data dify-data mqtt-data mqtt-logs sap-bridge-logs watchdog-logs prometheus-data grafana-data"

echo "=== Volume Restore ==="
echo "  Source: ${RESTORE_DIR}"
echo ""

echo "WARNING: This will OVERWRITE all named volumes and stop services."
read -rp "Continue? (y/N) " CONFIRM
if [ "${CONFIRM}" != "y" ] && [ "${CONFIRM}" != "Y" ]; then
    echo "Cancelled."; exit 0
fi

echo "Stopping services..."
docker compose -f "${COMPOSE_FILE}" stop

FAILED=0
for vol in ${VOLUMES}; do
    ARCHIVE="${RESTORE_DIR}/${vol}.tar.gz"
    [ ! -f "${ARCHIVE}" ] && echo "  Skipping ${vol} (not found)" && continue

    echo "  Restoring ${vol}..."
    docker volume inspect "${vol}" >/dev/null 2>&1 || docker volume create "${vol}" >/dev/null
    if docker run --rm -v "${vol}:/dest" -v "${RESTORE_DIR}:/backup:ro" alpine:3.19 tar xzf "/backup/${vol}.tar.gz" -C /dest; then
        echo "    OK: ${vol}"
    else
        echo "    FAILED: ${vol}"
        FAILED=$((FAILED + 1))
    fi
done

echo "Restarting services..."
docker compose -f "${COMPOSE_FILE}" up -d

echo ""
echo "=== Restore Complete ==="
if [ "${FAILED}" -eq 0 ]; then echo "  All volumes restored OK"; else echo "  ${FAILED} volume(s) failed"; fi
