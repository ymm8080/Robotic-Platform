#!/bin/bash
# =============================================================================
# Export Node-RED Flows for Git Versioning
# SAP-EWM Robot Dispatch Platform v3.4
#
# Exports current Node-RED flows from the running container into
# individual files by tab, plus a full backup.
# =============================================================================
set -euo pipefail

FLOWS_DIR="$(dirname "$0")/../nodered/flows"
BACKUP_DIR="${FLOWS_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CONTAINER="robot-platform-nodered"

mkdir -p "${FLOWS_DIR}" "${BACKUP_DIR}"

echo "=== Node-RED Flow Export ==="
echo "Timestamp: ${TIMESTAMP}"

# Method 1: Export from running container via HTTP API
echo ""
echo "[1/3] Exporting from Node-RED container..."
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    # Full export
    docker exec "${CONTAINER}" curl -s http://localhost:1880/flows \
        > "${BACKUP_DIR}/flows-full-${TIMESTAMP}.json" 2>/dev/null || {
        echo "  ⚠️  HTTP export failed, trying filesystem..."
    }

    # Filesystem copy
    docker cp "${CONTAINER}:/data/flows.json" "${BACKUP_DIR}/flows-${TIMESTAMP}.json" 2>/dev/null || true
    docker cp "${CONTAINER}:/data/flows_cred.json" "${BACKUP_DIR}/flows_cred-${TIMESTAMP}.json" 2>/dev/null || true
else
    echo "  ⚠️  Container ${CONTAINER} not running — using local file"
fi

# Method 2: Use local file (always available)
echo "[2/3] Processing local flows.json..."
LOCAL_FLOWS="$(dirname "$0")/../nodered/flows.json"
if [ -f "${LOCAL_FLOWS}" ]; then
    cp "${LOCAL_FLOWS}" "${BACKUP_DIR}/flows-local-${TIMESTAMP}.json"

    # Extract tabs and split into per-tab files
    TABS=$(python3 -c "
import json, sys
with open('${LOCAL_FLOWS}', 'r') as f:
    flows = json.load(f)
tabs = {n['id']: n.get('label', 'untitled') for n in flows if n.get('type') == 'tab'}
for tid, label in tabs.items():
    safe = label.replace('/', '_').replace(' ', '_')
    nodes = [n for n in flows if n.get('z') == tid or n.get('type') == 'tab' and n['id'] == tid]
    out = json.dumps(nodes, indent=2, ensure_ascii=False)
    path = '${FLOWS_DIR}/tab_${TIMESTAMP}_' + safe + '.json'
    with open(path, 'w') as out_f:
        out_f.write(out)
    print(f'  📄 {safe}: {len(nodes)} nodes → tab_{TIMESTAMP}_{safe}.json')
" 2>&1) || true
    echo "${TABS}"
fi

# Method 3: Create versioned symlink
echo "[3/3] Creating versioned reference..."
ln -sf "flows.json" "${FLOWS_DIR}/current.json" 2>/dev/null || cp "${LOCAL_FLOWS}" "${FLOWS_DIR}/current.json" 2>/dev/null || true

echo ""
echo "✅ Export complete"
echo "   Full backup: ${BACKUP_DIR}/flows-${TIMESTAMP}.json"
echo "   Tabs: ${FLOWS_DIR}/tab_${TIMESTAMP}_*.json"
echo ""
echo "To restore: docker cp ${BACKUP_DIR}/flows-${TIMESTAMP}.json ${CONTAINER}:/data/flows.json"
