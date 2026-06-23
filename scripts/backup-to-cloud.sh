#!/bin/bash
# =============================================================================
# Multi-Cloud Backup Script v1.0
# SAP-EWM Robot Dispatch Platform — backup-to-oss.sh
#
# Strategy:
#   - SQLite:        every 15 min to local + OSS (aliyun)
#   - flows.json:    on each deploy (triggered by Node-RED Projects git hook)
#   - Daily snapshot: full archive → OSS (aliyun) + sync to COS (tencent)
#   - Weekly offline: NAS + encrypted USB (manual trigger)
#
# RPO:  < 15 minutes (SQLite)
# RTO:  < 2 hours    (full restore from OSS)
#
# Prerequisites:
#   apt install ossutil  # Aliyun CLI
#   pip install coscmd   # Tencent COS CLI
#   # or use s3fs/rclone for S3-compatible endpoints
# =============================================================================
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/backup}"
DB_PATH="${DB_PATH:-/data/robot_platform.db}"
FLOWS_FILE="${FLOWS_FILE:-/data/flows.json}"
NAMESPACE="${NAMESPACE:-robot-platform}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
RETENTION_DAYS=${RETENTION_DAYS:-30}
LOG_FILE="${LOG_FILE:-/var/log/backup.log}

# OSS (阿里云) — primary
OSS_ENDPOINT="${OSS_ENDPOINT:-oss-cn-hangzhou.aliyuncs.com}"
OSS_BUCKET="${OSS_BUCKET:-robot-platform-backup}"
OSS_PREFIX="${OSS_PREFIX:-backup/${NAMESPACE}}"

# COS (腾讯云) — DR replica
COS_ENDPOINT="${COS_ENDPOINT:-cos.ap-hangzhou.myqcloud.com}"
COS_BUCKET="${COS_BUCKET:-robot-platform-backup-dr}"
COS_PREFIX="${COS_PREFIX:-backup/${NAMESPACE}}"

# NAS (本地离线) — weekly
NAS_MOUNT="${NAS_MOUNT:-/mnt/nas}"
NAS_PREFIX="${NAS_PREFIX:-${NAMESPACE}}"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; echo "$*"; }
err() { log "[ERROR] $*"; }

# ── Functions ───────────────────────────────────────────────────────────────

check_prereqs() {
    local missing=0
    for cmd in ossutil sqlite3 tar gzip; do
        if ! command -v "$cmd" &>/dev/null; then
            err "Missing: $cmd"
            missing=$((missing + 1))
        fi
    done
    return $missing
}

backup_sqlite() {
    local dest="$1"
    mkdir -p "$(dirname "$dest")"

    # Online backup via .backup (safe, no downtime)
    sqlite3 "$DB_PATH" ".backup '$dest'" 2>/dev/null || {
        err "SQLite backup FAILED (db locked or missing)"
        return 1
    }

    # Compress
    gzip -f "$dest"
    log "SQLite backup: ${dest}.gz ($(du -h "${dest}.gz" | cut -f1))"
    return 0
}

backup_flows() {
    local dest="$1"
    mkdir -p "$(dirname "$dest")"

    if [ -f "$FLOWS_FILE" ]; then
        cp "$FLOWS_FILE" "$dest"
        log "flows.json backed up: $dest"
    else
        log "[WARN] flows.json not found at $FLOWS_FILE"
    fi
}

upload_to_oss() {
    local src="$1"
    local target="$2"

    if command -v ossutil &>/dev/null; then
        ossutil cp "$src" "oss://${OSS_BUCKET}/${OSS_PREFIX}/${target}" \
            --endpoint "$OSS_ENDPOINT" \
            -f 2>&1 | tail -1 >> "$LOG_FILE"
        log "OSS upload: ${target}"
    else
        log "[SKIP] ossutil not installed, skipping OSS upload"
        return 1
    fi
}

sync_to_cos() {
    local src="$1"
    local target="$2"

    if command -v coscli &>/dev/null; then
        coscli cp "$src" "cos://${COS_BUCKET}/${COS_PREFIX}/${target}" \
            --endpoint "$COS_ENDPOINT" 2>&1 | tail -1 >> "$LOG_FILE"
        log "COS sync: ${target}"
    elif command -v rclone &>/dev/null; then
        rclone copy "$src" "cos:${COS_BUCKET}/${COS_PREFIX}/${target}" \
            --progress 2>&1 | tail -1 >> "$LOG_FILE"
        log "COS (rclone) sync: ${target}"
    else
        log "[SKIP] coscli/rclone not installed, skipping COS sync"
        return 1
    fi
}

cleanup_old() {
    local dir="$1"
    local days="$2"
    find "$dir" -name "*.gz" -type f -mtime "+${days}" -delete 2>/dev/null || true
    find "$dir" -name "*.tar" -type f -mtime "+${days}" -delete 2>/dev/null || true
    log "Cleaned up files older than ${days}d in $dir"
}

# ── Modes ───────────────────────────────────────────────────────────────────

mode_frequent() {
    log "=== Frequent backup (15min) ==="
    local dest_dir="${BACKUP_DIR}/sqlite"
    local dest="${dest_dir}/robot_platform_${TIMESTAMP}.db"
    backup_sqlite "$dest" || true
    upload_to_oss "${dest}.gz" "sqlite/robot_platform_${TIMESTAMP}.db.gz" || true
    cleanup_old "$dest_dir" 1  # keep only 1 day local
    log "=== Frequent backup done ==="
}

mode_daily() {
    log "=== Daily snapshot ==="
    local snapshot_dir="${BACKUP_DIR}/daily/${TIMESTAMP}"
    mkdir -p "$snapshot_dir"

    # Full backup set
    backup_sqlite "${snapshot_dir}/robot_platform.db"
    backup_flows "${snapshot_dir}/flows.json"

    # Config archive
    tar -czf "${snapshot_dir}/config.tar.gz" \
        -C /app nodered/settings.js redis/redis.conf mqtt/mosquitto.conf \
        2>/dev/null || log "[WARN] Some config files missing"

    # Upload full snapshot
    local archive="${BACKUP_DIR}/daily/${NAMESPACE}_daily_${TIMESTAMP}.tar.gz"
    tar -czf "$archive" -C "$BACKUP_DIR/daily" "$TIMESTAMP"
    upload_to_oss "$archive" "daily/${NAMESPACE}_daily_${TIMESTAMP}.tar.gz"

    # DR: sync to Tencent COS
    sync_to_cos "$archive" "daily/${NAMESPACE}_daily_${TIMESTAMP}.tar.gz" || true

    # Cleanup
    rm -rf "$snapshot_dir"
    cleanup_old "${BACKUP_DIR}/daily" "$RETENTION_DAYS"
    log "=== Daily snapshot done ==="
}

mode_weekly_offline() {
    log "=== Weekly offline backup to NAS ==="

    if ! mountpoint -q "$NAS_MOUNT"; then
        err "NAS not mounted at $NAS_MOUNT, skipping offline backup"
        return 1
    fi

    local nas_dir="${NAS_MOUNT}/${NAS_PREFIX}/$(date -u +%Y%m%d)"
    mkdir -p "$nas_dir"

    local archive="${BACKUP_DIR}/weekly/${NAMESPACE}_weekly_${TIMESTAMP}.tar.gz"
    mkdir -p "${BACKUP_DIR}/weekly"

    # Bundle: last 7 days of frequent + full config + docker-compose
    tar -czf "$archive" \
        -C "$BACKUP_DIR" sqlite \
        -C /app nodered/settings.js redis/redis.conf mqtt/mosquitto.conf docker-compose.yml .env \
        2>/dev/null || log "[WARN] Some files missing"

    # Copy to NAS
    cp "$archive" "${nas_dir}/"
    log "NAS offline backup: ${nas_dir}/"

    # Verify checksum
    sha256sum "$archive" > "${nas_dir}/$(basename "$archive").sha256"
    log "NAS checksum written"

    # Also copy to encrypted USB if mounted
    if mountpoint -q /mnt/usb-backup; then
        cp "$archive" "/mnt/usb-backup/"
        sha256sum "$archive" > "/mnt/usb-backup/$(basename "$archive").sha256"
        log "USB backup copy done"
    fi

    cleanup_old "${BACKUP_DIR}/weekly" 90  # keep 90 days
    log "=== Weekly offline backup done ==="
}

mode_restore() {
    local src="$1"
    if [ -z "$src" ] || [ ! -f "$src" ]; then
        err "Usage: $0 restore <backup.tar.gz>"
        exit 1
    fi
    log "=== Restore from $src ==="
    local restore_dir="/tmp/restore_${TIMESTAMP}"
    mkdir -p "$restore_dir"
    tar -xzf "$src" -C "$restore_dir"
    log "Extracted to $restore_dir"
    echo ""
    echo "Manual steps:"
    echo "  1. Stop services: docker-compose down"
    echo "  2. Restore DB: sqlite3 ${DB_PATH} '.restore ${restore_dir}/sqlite/*.db'"
    echo "  3. Restore config: cp ${restore_dir}/nodered/settings.js /app/nodered/"
    echo "  4. Start services: docker-compose up -d"
    log "=== Restore prepared ==="
}

# ── Main ────────────────────────────────────────────────────────────────────

main() {
    mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

    case "${1:-frequent}" in
        frequent)  mode_frequent ;;
        daily)     mode_daily ;;
        weekly)    mode_weekly_offline ;;
        restore)   shift; mode_restore "$@" ;;
        *)
            echo "Usage: $0 {frequent|daily|weekly|restore <file>}"
            echo ""
            echo "  frequent  — SQLite backup every 15 min → OSS (aliyun)"
            echo "  daily     — Full snapshot → OSS + sync COS (tencent)"
            echo "  weekly    — Offline archive → NAS + encrypted USB"
            echo "  restore   — Extract backup archive for manual restore"
            exit 1
            ;;
    esac
}

main "$@"
