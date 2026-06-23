#!/bin/bash
# =============================================================================
# SQLite → PostgreSQL Data Migration Script v1.0
# SAP-EWM Robot Dispatch Platform — v3.4→v4.0 升级
#
# Usage:
#   export PG_URI="postgresql://user:pass@localhost:5432/robot_platform"
#   bash scripts/data-migration-sqlite-to-pg.sh
#
# Migration process:
#   1. Dump SQLite schema + data to SQL
#   2. Transform SQLite-specific syntax → PostgreSQL
#   3. Load into PostgreSQL
#   4. Verify row counts match
#   5. Generate rollback script
#
# Rollback:
#   bash scripts/data-migration-sqlite-to-pg.sh rollback
# =============================================================================
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
SQLITE_DB="${DB_PATH:-/data/robot_platform.db}"
PG_URI="${PG_URI:-postgresql://robot_platform:changeme@localhost:5432/robot_platform}"
TEMP_DIR="${TEMP_DIR:-/tmp/sqlite-to-pg-migration}"
LOG_FILE="${LOG_FILE:-/var/log/migration-sqlite-to-pg.log}"
NAMESPACE="${NAMESPACE:-robot-platform}"
BACKUP_DIR="${BACKUP_DIR:-/backup/pre-migration}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)

# Tables to migrate (in dependency order)
TABLES=(
    "schema_version"
    "data_mask_rules"
    "dispatch_rules"
    "robot_status"
    "zone_lock"
    "orders"
    "outbox_events"
    "audit_log"
    "dead_letter_queue"
    "api_deviation_log"
)

log()   { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] [MIGRATE] $*" | tee -a "$LOG_FILE"; }
err()   { log "[ERROR] $*"; }
die()   { err "$*"; exit 1; }

# ── Prerequisites ───────────────────────────────────────────────────────────

check_prereqs() {
    local missing=0
    for cmd in sqlite3 psql pg_isready perl; do
        if ! command -v "$cmd" &>/dev/null; then
            err "Missing: $cmd"
            missing=$((missing + 1))
        fi
    done

    if [ $missing -gt 0 ]; then
        die "Install missing tools: apt install sqlite3 postgresql-client"
    fi

    # Check PostgreSQL connectivity
    if ! pg_isready -d "$PG_URI" &>/dev/null; then
        die "PostgreSQL not reachable at $PG_URI"
    fi
    log "Prerequisites OK"
}

# ── Step 1: Backup SQLite ───────────────────────────────────────────────────

step_backup() {
    log "=== Step 1: Backing up SQLite database ==="
    mkdir -p "$BACKUP_DIR"

    local backup_path="${BACKUP_DIR}/robot_platform_pre_migration_${TIMESTAMP}.db"
    sqlite3 "$SQLITE_DB" ".backup '$backup_path'" 2>/dev/null || \
        die "SQLite backup FAILED at $SQLITE_DB"

    gzip -f "$backup_path"
    log "SQLite backup: ${backup_path}.gz ($(du -h "${backup_path}.gz" | cut -f1))"
}

# ── Step 2: Dump SQLite schema ──────────────────────────────────────────────

step_dump_schema() {
    log "=== Step 2: Dumping SQLite schema ==="
    mkdir -p "$TEMP_DIR"

    # Dump only CREATE TABLE/INDEX statements (no data)
    sqlite3 "$SQLITE_DB" ".schema" > "${TEMP_DIR}/sqlite_schema.sql" 2>/dev/null || \
        die "SQLite schema dump FAILED"

    local table_count=$(grep -c "CREATE TABLE" "${TEMP_DIR}/sqlite_schema.sql")
    log "Dumped $table_count tables from SQLite"
}

# ── Step 3: Transform SQL → PostgreSQL ──────────────────────────────────────

step_transform() {
    log "=== Step 3: Transforming SQL to PostgreSQL dialect ==="
    local input="${TEMP_DIR}/sqlite_schema.sql"
    local output="${TEMP_DIR}/pg_schema.sql"

    perl -pe '
        s/INTEGER PRIMARY KEY/SERIAL PRIMARY KEY/g;
        s/INTEGER NOT NULL DEFAULT 1/INTEGER NOT NULL DEFAULT 1/g;
        s/REAL/NUMERIC(10, 2)/g;
        s/TEXT DEFAULT \(datetime\(.now.\)\)/TIMESTAMPTZ NOT NULL DEFAULT NOW()/g;
        s/TEXT DEFAULT \(datetime\(\047now\047\)\)/TIMESTAMPTZ NOT NULL DEFAULT NOW()/g;
        s/datetime\(.now.\)/NOW()/g;
        s/CREATE TABLE IF NOT EXISTS orders_v2/CREATE TABLE IF NOT EXISTS orders/g;
        s/orders_v2/orders/g;
        s/"([^"]+)"/\L$1/g;
    ' "$input" > "$output"

    # Prepend PG-specific header
    local header="-- PostgreSQL schema (auto-converted from SQLite $(basename "$SQLITE_DB"))
-- Migration timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')
SET synchronous_commit = on;
BEGIN;
"
    echo "$header" | cat - "$output" > "${TEMP_DIR}/pg_schema_prefixed.sql"
    mv "${TEMP_DIR}/pg_schema_prefixed.sql" "$output"

    log "Schema transformed: $output"
}

# ── Step 4: Dump and transform data ─────────────────────────────────────────

step_dump_data() {
    log "=== Step 4: Dumping and transforming data ==="
    local data_file="${TEMP_DIR}/pg_data.sql"
    rm -f "$data_file"
    touch "$data_file"

    for table in "${TABLES[@]}"; do
        # Check if table exists in SQLite
        local exists=$(sqlite3 "$SQLITE_DB" ".tables $table" 2>/dev/null)
        if [ -z "$exists" ]; then
            log "  Table $table does not exist in SQLite, skipping"
            continue
        fi

        log "  Dumping $table ..."

        # Dump as INSERT statements with column names
        sqlite3 "$SQLITE_DB" -cmd ".mode insert $table" \
            -cmd ".headers on" \
            "SELECT * FROM $table;" 2>/dev/null >> "${TEMP_DIR}/raw_${table}.sql" || \
            log "  [WARN] Table $table may be empty"

        # Transform INSERT syntax
        perl -pe '
            s/^INSERT INTO /INSERT INTO /;
            s/datetime\(.now.\)/NOW()/g;
            s/datetime\(\047now\047\)/NOW()/g;
            s/"/'"'"'/g;  # SQLite double-quote strings → PG single-quote
        ' "${TEMP_DIR}/raw_${table}.sql" >> "$data_file" 2>/dev/null || true
    done

    local row_count=$(wc -l < "$data_file")
    log "Data dump complete: $row_count INSERT lines"
}

# ── Step 5: Load into PostgreSQL ────────────────────────────────────────────

step_load() {
    log "=== Step 5: Loading into PostgreSQL ==="

    # Apply schema first
    if [ -f "${TEMP_DIR}/pg_schema.sql" ]; then
        cp "${TEMP_DIR}/pg_schema.sql" "${TEMP_DIR}/pg_load.sql"
    else
        # Use the init-pg.sql if schema transform is empty
        log "Using canonical init-pg.sql for schema"
        cp "$(dirname "$0")/../sql/init-pg.sql" "${TEMP_DIR}/pg_load.sql"
    fi

    # Append data
    echo "" >> "${TEMP_DIR}/pg_load.sql"
    cat "${TEMP_DIR}/pg_data.sql" >> "${TEMP_DIR}/pg_load.sql"
    echo "COMMIT;" >> "${TEMP_DIR}/pg_load.sql"

    # Execute
    log "Loading schema + data into PostgreSQL..."
    if psql "$PG_URI" -f "${TEMP_DIR}/pg_load.sql" 2>&1 | tee -a "$LOG_FILE"; then
        log "PostgreSQL load completed successfully"
    else
        die "PostgreSQL load FAILED — check ${LOG_FILE} for details"
    fi
}

# ── Step 6: Verify ──────────────────────────────────────────────────────────

step_verify() {
    log "=== Step 6: Verifying data integrity ==="
    local errors=0
    local verified=0

    for table in "${TABLES[@]}"; do
        local sqlite_count=$(sqlite3 "$SQLITE_DB" "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
        local pg_count=$(psql "$PG_URI" -t -A -c "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")

        if [ "$sqlite_count" = "$pg_count" ]; then
            log "  ✅ $table: $pg_count rows (matched)"
            verified=$((verified + 1))
        else
            err "  ❌ $table: SQLite=$sqlite_count PG=$pg_count (MISMATCH)"
            errors=$((errors + 1))
        fi
    done

    log "Verified: $verified/${#TABLES[@]} tables match"
    if [ $errors -gt 0 ]; then
        die "$errors table(s) have mismatched row counts!"
    fi
    log "✅ Data integrity check PASSED"
}

# ── Step 7: Generate rollback ─────────────────────────────────────────────

step_rollback_script() {
    log "=== Step 7: Generating rollback script ==="
    local rollback="${BACKUP_DIR}/rollback_${TIMESTAMP}.sh"

    cat > "$rollback" << SCRIPT
#!/bin/bash
# Rollback script — generated $(date -u '+%Y-%m-%d %H:%M:%S UTC')
# Restores SQLite backup and drops PG tables
set -euo pipefail

echo "=== Rollback: Restoring SQLite ==="
# Restore from backup
sqlite3 "$SQLITE_DB" ".restore '${BACKUP_DIR}/robot_platform_pre_migration_${TIMESTAMP}.db'"
echo "SQLite restored from backup"

echo "=== Rollback: Dropping PG tables ==="
psql "$PG_URI" -c "DROP TABLE IF EXISTS $(IFS=,; echo "${TABLES[*]}") CASCADE;"
echo "PostgreSQL tables dropped"

echo "✅ Rollback complete — system returned to SQLite"
SCRIPT

    chmod +x "$rollback"
    log "Rollback script: $rollback"
}

# ── Main ────────────────────────────────────────────────────────────────────

main() {
    log "============================================"
    log "SQLite → PostgreSQL Migration"
    log "Source:      $SQLITE_DB"
    log "Target:      $PG_URI"
    log "Timestamp:   $TIMESTAMP"
    log "============================================"

    if [ "${1:-}" = "rollback" ]; then
        local latest_rollback=$(ls -t "${BACKUP_DIR}/rollback_"*.sh 2>/dev/null | head -1)
        if [ -z "$latest_rollback" ]; then
            die "No rollback script found in $BACKUP_DIR"
        fi
        log "Executing rollback: $latest_rollback"
        bash "$latest_rollback"
        log "Rollback complete"
        return 0
    fi

    # Full migration
    check_prereqs
    step_backup
    step_dump_schema
    step_transform
    step_dump_data
    step_load
    step_verify
    step_rollback_script

    log ""
    log "============================================"
    log "✅ Migration complete!"
    log ""
    log "Next steps:"
    log "  1. Update docker-compose.yml:"
    log "     - Uncomment postgres service"
    log "     - Change Node-RED DB_URL to postgres://..."
    log "  2. Update .env: PG_URI=$PG_URI"
    log "  3. Restart services: docker-compose down && docker-compose up -d"
    log "  4. Monitor: docker logs robot-platform-nodered --tail 100"
    log "  5. If issues: bash $(basename "$0") rollback"
    log "============================================"
}

main "$@"
