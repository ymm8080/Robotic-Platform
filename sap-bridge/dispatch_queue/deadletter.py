"""
Dead letter handler — manages orders that have exhausted retries.
Stores in SQLite dead_letter_queue with full error context.
"""
import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/data/robot_platform.db")


class DeadLetterHandler:
    """Handles orders that have exhausted all retry attempts."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def send(
        self,
        order_no: str,
        error_type: str,
        error_message: str,
        payload: Any | None = None,
        retry_count: int = 0,
    ) -> int:
        """Move an order to the dead letter queue. Returns deadletter ID."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO dead_letter_queue
                   (original_id, error_type, error_message, payload, status, created_at)
                   VALUES (?, ?, ?, ?, 'UNRESOLVED', ?)""",
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT * FROM dead_letter_queue
                   WHERE status = 'UNRESOLVED'
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_all(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List all deadletter items with pagination."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT * FROM dead_letter_queue
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def resolve(self, dl_id: int, resolution: str = "MANUAL_FIX") -> bool:
        """Mark a deadletter item as resolved."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """UPDATE dead_letter_queue
                   SET status = ?, error_message = error_message || ' | RESOLVED: ' || ?
                   WHERE id = ? AND status = 'UNRESOLVED'""",
                ("RESOLVED", resolution, dl_id),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def retry(self, dl_id: int) -> dict | None:
        """Retrieve a deadletter item for retry. Returns payload or None."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM dead_letter_queue WHERE id = ?", (dl_id,)
            ).fetchone()
            if row is None:
                return None
            data = dict(row)
            data["payload"] = json.loads(data["payload"]) if data.get("payload") else None
            return data
        finally:
            conn.close()

    def count_unresolved(self) -> int:
        """Count unresolved deadletter items."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM dead_letter_queue WHERE status = 'UNRESOLVED'"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
