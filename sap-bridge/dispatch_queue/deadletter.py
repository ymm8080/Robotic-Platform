"""
Dead letter handler — manages orders that have exhausted retries.
Stores in dead_letter_queue with full error context.

v4.1: PostgreSQL-only. All data in PostgreSQL.
"""
import json
import logging
from datetime import UTC, datetime
from typing import Any

from db import connect, init_schema

logger = logging.getLogger(__name__)


class DeadLetterHandler:
    """Handles orders that have exhausted all retry attempts."""

    def __init__(self):
        init_schema()

    def send(
        self,
        order_no: str,
        error_type: str,
        error_message: str,
        payload: Any | None = None,
        retry_count: int = 0,
    ) -> int:
        """Move an order to the dead letter queue. Returns deadletter ID."""
        conn = connect()
        try:
            sql = """
                INSERT INTO dead_letter_queue
                (original_id, error_type, error_message, payload, status, created_at)
                VALUES (?, ?, ?, ?, 'UNRESOLVED', ?)
                RETURNING id
            """
            cur = conn.execute(
                sql,
                (
                    order_no,
                    error_type,
                    error_message[:500],
                    json.dumps(payload) if payload else None,
                    _now(),
                ),
            )
            conn.commit()
            dl_id = cur.lastrowid
            logger.error(f"Deadletter created (id={dl_id}): {order_no} — {error_type}: {error_message}")
            return dl_id
        finally:
            conn.close()

    def list_unresolved(self, limit: int = 50) -> list[dict]:
        """List unresolved deadletter items."""
        conn = connect()
        try:
            rows = conn.execute(
                """SELECT * FROM dead_letter_queue
                   WHERE status = 'UNRESOLVED'
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return rows
        finally:
            conn.close()

    def list_all(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List all deadletter items with pagination."""
        conn = connect()
        try:
            rows = conn.execute(
                """SELECT * FROM dead_letter_queue
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            return rows
        finally:
            conn.close()

    def resolve(self, dl_id: int, resolution: str = "MANUAL_FIX") -> bool:
        """Mark a deadletter item as resolved."""
        conn = connect()
        try:
            cur = conn.execute(
                """UPDATE dead_letter_queue
                   SET status = ?, error_message = error_message || ' | RESOLVED: ' || ?
                   WHERE id = ? AND status = 'UNRESOLVED'""",
                ("RESOLVED", resolution, dl_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def retry(self, dl_id: int) -> dict | None:
        """Retrieve a deadletter item for retry. Returns payload or None."""
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM dead_letter_queue WHERE id = ?", (dl_id,)
            ).fetchone()
            if row is None:
                return None
            data = dict(row)
            payload_raw = data.get("payload")
            data["payload"] = payload_raw if isinstance(payload_raw, (dict, list)) else (json.loads(payload_raw) if payload_raw else None)
            return data
        finally:
            conn.close()

    def count_unresolved(self) -> int:
        """Count unresolved deadletter items."""
        conn = connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM dead_letter_queue WHERE status = 'UNRESOLVED'"
            ).fetchone()
            if row is None:
                return 0
            return row.get("cnt", 0) if isinstance(row, dict) else row[0]
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
