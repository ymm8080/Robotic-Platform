"""Shared test fixtures and configuration.

PostgreSQL-only: All tests connect to a PostgreSQL instance.
"""
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── PostgreSQL test configuration ──────────────────────────
# Priority: DB_URL (full URI) > PG_PASSWORD_FILE > PG_PASSWORD
# If none set, fall back to a local Docker default for dev convenience.
_pg_host = os.environ.get("PG_HOST", "localhost")
_pg_port = os.environ.get("PG_PORT", "5432")
_pg_db = os.environ.get("PG_DB", "robot_platform_test")
_pg_user = os.environ.get("PG_USER", "robot_platform")

if "DB_URL" not in os.environ:
    # Try secrets file (production-like)
    if "PG_PASSWORD" not in os.environ and "PG_PASSWORD_FILE" not in os.environ:
        _secrets_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "secrets", "pg_password.txt"
        )
        if os.path.exists(_secrets_path):
            os.environ["PG_PASSWORD_FILE"] = _secrets_path

    # If we have a password (env or secrets file), build URL from parts
    _pg_password = os.environ.get("PG_PASSWORD", "")
    _pg_password_file = os.environ.get("PG_PASSWORD_FILE", "")
    if _pg_password_file:
        try:
            with open(_pg_password_file) as f:
                _pg_password = f.read().strip()
        except OSError:
            pass

    if _pg_password:
        os.environ["DB_URL"] = (
            f"postgresql://{_pg_user}:{_pg_password}@{_pg_host}:{_pg_port}/{_pg_db}"
        )
    elif "PG_PASSWORD" not in os.environ and "PG_PASSWORD_FILE" not in os.environ:
        # Last resort: local Docker dev default (matches pg-test-robot container)
        os.environ.setdefault("PG_PASSWORD", "changeme_pg_password")
        os.environ["DB_URL"] = (
            f"postgresql://{_pg_user}:changeme_pg_password@{_pg_host}:{_pg_port}/{_pg_db}"
        )

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("REDIS_URL_TEST", "redis://localhost:6379/15")

# ── Session-scoped DB setup ────────────────────────────────

import gc
import logging

import pytest

logger = logging.getLogger(__name__)

_PG_AVAILABLE: bool | None = None


def _pg_available() -> bool:
    """Check if PostgreSQL is reachable (cached after first call)."""
    global _PG_AVAILABLE
    if _PG_AVAILABLE is not None:
        return _PG_AVAILABLE
    try:
        from db import connect
        conn = connect()
        conn.commit()  # Close any implicit transaction
        conn.close()
        _PG_AVAILABLE = True
    except Exception:
        _PG_AVAILABLE = False
    return _PG_AVAILABLE


def _truncate_tables():
    """Truncate all data tables using raw psycopg2 (bypasses ConnectionWrapper)."""
    import psycopg2

    from db import DB_URL
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "TRUNCATE TABLE orders, dead_letter_queue, outbox_events, "
        "brand_calibrations, map_zones, map_edges, map_nodes, "
        "facility_maps CASCADE"
    )
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def _init_pg_schema():
    """Create schema once per test session."""
    if not _pg_available():
        logger.warning(
            "PostgreSQL not available — DB-dependent tests will fail. "
            "Start PostgreSQL with: docker run -d --name pg-test -p 5432:5432 "
            "-e POSTGRES_DB=robot_platform_test -e POSTGRES_USER=robot_platform "
            "-e POSTGRES_PASSWORD=<password> postgres:15-alpine"
        )
        yield
        return

    from db import init_schema
    init_schema()
    logger.info("PostgreSQL schema initialized for test session")
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all data tables before each test for isolation."""
    if not _pg_available():
        yield
        return

    # Force GC to release any unclosed cursors/connections from previous test
    gc.collect()

    _truncate_tables()
    yield
