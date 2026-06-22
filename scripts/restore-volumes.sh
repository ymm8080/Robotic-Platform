#!/bin/bash
# =============================================================================
# Volume Restore Script — SAP-EWM Robot Dispatch Platform
# Restore Docker volumes from a timestamped backup directory.
# Usage: ./scripts/restore-volumes.sh <backup_dir>
# Example: ./scripts/restore-volumes.sh "D:/EWM ROBOT/backups/20260621_143000"
# =============================================================================
set -euo pipefail

RESTORE_FROM="${1:-}"
COMPOSE_FILE="D:/EWM ROBOT/ROBOTIC PLATFORM CODES/docker-compose.yml"

if [ -z "${RESTORE_FROM}" ]; then
  echo "ERROR: Usage: $0 <backup_dir>"
  echo "  Available backups:"
  ls -d "${BACKUP_DIR:-D:/EWM ROBOT/backups}"/*/ 2>/dev/null | head -10 || echo "  (none found)"
  exit 1
fi

if [ ! -d "${RESTORE_FROM}" ]; then
  echo "ERROR: Backup directory not found: ${RESTORE_FROM}"
  exit 1
fi

echo "=== Restore from: ${RESTORE_FROM} ==="
cat "${RESTORE_FROM}/MANIFEST.txt" 2>/dev/null || echo "  (no manifest)"
echo ""

# Confirm
read -p "This will OVERWRITE all current volume data. Continue? (y/N) " CONFIRM
if [ "${CONFIRM}" != "y" ] && [ "${CONFIRM}" != "Y" ]; then
  echo "Aborted."
  exit 0
fi

# Find all tar.gz files
for archive in "${RESTORE_FROM}"/*.tar.gz; do
  vol_name=$(basename "${archive}" .tar.gz)

  echo "[$(date +%H:%M:%S)] Restoring ${vol_name}..."

  # Stop any container using this volume
  docker compose -f "${COMPOSE_FILE}" stop 2>/dev/null || true

  # Remove existing volume data (but keep the volume itself)
  docker run --rm -v "${vol_name}:/target" alpine:3.19 sh -c "rm -rf /target/* /target/.* 2>/dev/null || true"

  # Extract backup into volume
  docker run --rm \
    -v "${vol_name}:/target" \
    -v "${RESTORE_FROM}:/backup:ro" \
    alpine:3.19 \
    tar xzf "/backup/${vol_name}.tar.gz" -C /target

  echo "  → ${vol_name} restored"
done

# Restart all services
echo "[$(date +%H:%M:%S)] Restarting services..."
docker compose -f "${COMPOSE_FILE}" up -d

echo "[$(date +%H:%M:%S)] Restore complete. Run 'docker compose ps' to verify."
