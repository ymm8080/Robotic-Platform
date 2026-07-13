"""
Database layer — PostgreSQL only (v4.1).

All data lives in PostgreSQL. No SQLite fallback.
Tests must connect to a running PostgreSQL instance (see conftest.py).

Connection config via env vars:
  DB_URL=postgresql://user:pass@host:port/db   (full URL, highest priority)
  PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD (or PG_PASSWORD_FILE for Docker Secrets)
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# ── Connection URL ─────────────────────────────────────────


def _build_pg_url() -> str:
    """Build PostgreSQL connection URL from env vars or Docker Secrets.

    Priority:
    1. DB_URL env var (full connection string)
    2. PG_PASSWORD_FILE (Docker Secret) + PG_HOST/PORT/DB/USER
    3. PG_PASSWORD env var + PG_HOST/PORT/DB/USER
    """
    db_url = os.getenv("DB_URL", "")
    if db_url:
        return db_url

    pg_password = ""
    pg_password_file = os.getenv("PG_PASSWORD_FILE", "")
    if pg_password_file:
        try:
            with open(pg_password_file) as f:
                pg_password = f.read().strip()
        except OSError:
            logger.warning(f"Cannot read PG password from {pg_password_file}")
    else:
        pg_password = os.getenv("PG_PASSWORD", "")

    if not pg_password:
        raise RuntimeError(
            "No PostgreSQL connection configured. Set DB_URL or PG_PASSWORD/PG_PASSWORD_FILE. "
            "SQLite is no longer supported."
        )

    pg_host = os.getenv("PG_HOST", "postgres")
    pg_port = os.getenv("PG_PORT", "5432")
    pg_db = os.getenv("PG_DB", "robot_platform")
    pg_user = os.getenv("PG_USER", "robot_platform")

    return f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"


DB_URL = _build_pg_url()

# ── Placeholder translation (? → %s) ───────────────────────
# Callers use ? placeholders for readability; translated to %s for psycopg2.

_PLACEHOLDER_RE = re.compile(r"(?<!%)\?")


def _translate_sql(sql: str) -> str:
    """Translate ? placeholders to PostgreSQL %s."""
    return _PLACEHOLDER_RE.sub("%s", sql)


# ── Cursor wrapper ─────────────────────────────────────────


class CursorWrapper:
    """Thin wrapper around psycopg2 RealDictCursor."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._pg_lastrowid: int | None = None

    @property
    def lastrowid(self) -> int | None:
        return self._pg_lastrowid

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def execute(self, sql: str, params: tuple = ()) -> "CursorWrapper":
        self._cursor.execute(_translate_sql(sql), params)
        return self

    def fetchone(self) -> dict | None:
        row = self._cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self) -> list[dict]:
        return [dict(r) for r in self._cursor.fetchall()]

    def close(self):
        self._cursor.close()


# ── Connection wrapper ─────────────────────────────────────


class ConnectionWrapper:
    """Thin wrapper around psycopg2 connection."""

    def __init__(self, conn):
        self._conn = conn

    @property
    def backend(self) -> str:
        return "postgresql"

    def execute(self, sql: str, params: tuple = ()) -> CursorWrapper:
        """Execute SQL. Handles INSERT...RETURNING for lastrowid."""
        pg_cur = self._conn.cursor()
        translated = _translate_sql(sql)
        pg_cur.execute(translated, params)

        stripped = sql.strip().upper()
        if stripped.startswith("INSERT") and "RETURNING" in sql.upper():
            row = pg_cur.fetchone()
            if row:
                wrapper = CursorWrapper(pg_cur)
                wrapper._pg_lastrowid = row[0] if isinstance(row, (tuple, list)) else list(row.values())[0]
                return wrapper
        return CursorWrapper(pg_cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def row_factory(self, _factory):
        """No-op — PG uses RealDictCursor."""
        pass


# ── Connection factory ─────────────────────────────────────


def connect() -> ConnectionWrapper:
    """Get a PostgreSQL connection."""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        raise RuntimeError("psycopg2 is not installed. Run: pip install psycopg2-binary")
    conn = psycopg2.connect(DB_URL)
    conn.cursor_factory = RealDictCursor
    logger.debug("PostgreSQL connection established")
    return ConnectionWrapper(conn)


# ── Schema initialization ──────────────────────────────────


def init_schema():
    """Create tables if they don't exist (PostgreSQL only)."""
    conn = connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id              SERIAL PRIMARY KEY,
                order_no        TEXT NOT NULL UNIQUE,
                type            TEXT NOT NULL DEFAULT 'MOVE'
                                    CHECK(type IN ('PICK', 'PUT', 'MOVE', 'CHARGE')),
                priority        INTEGER NOT NULL DEFAULT 3
                                    CHECK(priority >= 0 AND priority <= 3),
                source          TEXT,
                robot_brand     TEXT,
                robot_serial    TEXT,
                status          TEXT NOT NULL DEFAULT 'CREATED'
                                    CHECK(status IN (
                                        'CREATED', 'ASSIGNED', 'IN_PROGRESS',
                                        'COMPLETED', 'FAILED', 'CANCELLED',
                                        'SUSPENDED', 'DIFF_SUSPENDED',
                                        'SAP_PENDING', 'SAP_CONFIRMED'
                                    )),
                payload         JSONB,
                zone_id         TEXT,
                zone_token      TEXT,
                weight          NUMERIC(10, 2),
                location        TEXT,
                env_tag         TEXT DEFAULT 'PROD',
                expected_qty    INTEGER,
                assigned_rule_id INTEGER,
                error_message   TEXT,
                version         INTEGER NOT NULL DEFAULT 1,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at    TIMESTAMPTZ
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id              SERIAL PRIMARY KEY,
                original_id     TEXT,
                error_type      TEXT,
                error_message   TEXT,
                payload         JSONB,
                status          TEXT NOT NULL DEFAULT 'UNRESOLVED'
                                    CHECK(status IN ('UNRESOLVED', 'RESOLVED', 'RETRIED')),
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at     TIMESTAMPTZ,
                resolution      TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dlq_status ON dead_letter_queue(status)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS outbox_events (
                id              SERIAL PRIMARY KEY,
                order_id        INTEGER NOT NULL,
                event_type      TEXT NOT NULL,
                payload         JSONB,
                status          TEXT NOT NULL DEFAULT 'PENDING'
                                    CHECK(status IN ('PENDING', 'SENT', 'FAILED')),
                retry_count     INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                sent_at         TIMESTAMPTZ,
                last_error      TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_events(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_order ON outbox_events(order_id)")

        # ── Shared canonical facility map tables ────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facility_maps (
                id              SERIAL PRIMARY KEY,
                name            TEXT NOT NULL,
                version         INTEGER NOT NULL DEFAULT 1,
                map_data        JSONB DEFAULT '{}',
                origin_x        DOUBLE PRECISION DEFAULT 0,
                origin_y        DOUBLE PRECISION DEFAULT 0,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(name, version)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS map_nodes (
                id              SERIAL PRIMARY KEY,
                map_id          INTEGER NOT NULL REFERENCES facility_maps(id),
                node_id         TEXT NOT NULL,
                x               DOUBLE PRECISION NOT NULL,
                y               DOUBLE PRECISION NOT NULL,
                theta           DOUBLE PRECISION DEFAULT 0,
                properties      JSONB DEFAULT '{}',
                UNIQUE(map_id, node_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_nodes_map ON map_nodes(map_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS map_edges (
                id              SERIAL PRIMARY KEY,
                map_id          INTEGER NOT NULL REFERENCES facility_maps(id),
                edge_id         TEXT NOT NULL,
                start_node_id   TEXT NOT NULL,
                end_node_id     TEXT NOT NULL,
                properties      JSONB DEFAULT '{}',
                UNIQUE(map_id, edge_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_edges_map ON map_edges(map_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS map_zones (
                id              SERIAL PRIMARY KEY,
                map_id          INTEGER NOT NULL REFERENCES facility_maps(id),
                zone_id         TEXT NOT NULL,
                zone_type       TEXT NOT NULL DEFAULT 'EXCLUSION'
                                    CHECK(zone_type IN ('EXCLUSION', 'CHARGING', 'STAGING', 'PICKING', 'CUSTOM')),
                polygon         JSONB NOT NULL,
                properties      JSONB DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_zones_map ON map_zones(map_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_calibrations (
                id              SERIAL PRIMARY KEY,
                brand           TEXT NOT NULL,
                map_id          INTEGER NOT NULL REFERENCES facility_maps(id),
                scale_x         DOUBLE PRECISION DEFAULT 1.0,
                scale_y         DOUBLE PRECISION DEFAULT 1.0,
                shear           DOUBLE PRECISION DEFAULT 0.0,
                rotation_deg    DOUBLE PRECISION DEFAULT 0.0,
                translate_x     DOUBLE PRECISION DEFAULT 0.0,
                translate_y     DOUBLE PRECISION DEFAULT 0.0,
                reference_points JSONB NOT NULL DEFAULT '[]',
                residual_error_mm DOUBLE PRECISION,
                calibrated_at   TIMESTAMPTZ DEFAULT NOW(),
                calibrated_by   TEXT,
                valid_until     TIMESTAMPTZ,
                UNIQUE(brand, map_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calibrations_brand ON brand_calibrations(brand)")

        conn.commit()
        logger.info("Schema initialized (PostgreSQL)")
    finally:
        conn.close()
