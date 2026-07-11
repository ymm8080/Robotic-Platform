"""WORM 黑匣子 — Write-Once-Read-Many (陷阱 #12 取证黑洞, 灰犀牛 #5/#10).

铁律三: 5分钟内还原完整因果链.
- Append-only: records are hash-chained (each record stores the previous
  record's hash) so tampering is detectable.
- 24h/文件 分片滚动, 180天保留 (灰犀牛 #5).
- 磁盘剩余 < 20% 告警 (Runbook 图6) — surfaced via disk_warning().
- All ERR_* events, E-Stops, manual interventions, boot takeovers and
  shadow mismatches are written here; this is the legal evidence trail.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from core.config import WormConfig


@dataclass
class WormRecord:
    timestamp: float
    category: str        # "EVENT" | "ERROR" | "ESTOP" | "MANUAL" | "BOOT" | "MISMATCH"
    robot_id: str
    payload: dict        # structured cause context
    prev_hash: str = ""
    hash: str = ""


class WormBlackbox:
    """Append-only, hash-chained causal ledger."""

    def __init__(
        self,
        config: WormConfig | None = None,
        sink_path: Path | None = None,
        disk_free_pct: float = 100.0,
        mode: str = "PRODUCTION",
    ) -> None:
        self.cfg = config or WormConfig()
        self._sink = sink_path
        self._prev_hash = ""
        self._records: list[WormRecord] = []
        self._disk_free_pct = disk_free_pct
        self._current_shard_start: float = 0.0
        self._shard_dir = sink_path.parent if sink_path else None
        self._base_name = sink_path.stem if sink_path else None
        self._mode = mode
        self._sink_failed = False
        self._lock = threading.Lock()
        if sink_path is not None:
            self._load_from_disk()

    def write(self, timestamp: float, category: str, robot_id: str, payload: dict) -> WormRecord:
        """Append one record. Never overwrites; chains on the previous hash."""
        with self._lock:
            if self._sink is not None and self.needs_rotation(timestamp):
                self.rotate(timestamp)
            rec = WormRecord(
                timestamp=timestamp,
                category=category,
                robot_id=robot_id,
                payload=payload,
                prev_hash=self._prev_hash,
            )
            rec.hash = self._hash_record(rec)
            self._records.append(rec)
            self._prev_hash = rec.hash
            if self._sink is not None:
                self._persist(rec)
            return rec

    def _hash_record(self, rec: WormRecord) -> str:
        blob = json.dumps(
            {
                "timestamp": rec.timestamp,
                "category": rec.category,
                "robot_id": rec.robot_id,
                "payload": rec.payload,
                "prev_hash": rec.prev_hash,
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(blob).hexdigest()

    def verify_chain(self) -> bool:
        """Tamper check: recompute every hash and confirm the chain links."""
        prev = ""
        for rec in self._records:
            if rec.prev_hash != prev:
                return False
            if self._hash_record(rec) != rec.hash:
                return False
            prev = rec.hash
        return True

    def replay(self, robot_id: str | None = None, since: float = 0.0) -> list[WormRecord]:
        """因果链回放 — Playback一键导出故障前后30秒上下文 (Runbook §5)."""
        return [
            r for r in self._records
            if r.timestamp >= since and (robot_id is None or r.robot_id == robot_id)
        ]

    def replay_recent(self, duration_seconds: float, robot_id: str | None = None, now: float | None = None) -> list[WormRecord]:
        """Convenience: replay from monotonic time minus ``duration_seconds``.

        Uses ``time.monotonic()`` (same clock as WORM record timestamps) so the
        time window is consistent on all platforms.  Pass ``now`` to override the
        reference time in tests.
        """
        import time as _time
        if now is None:
            now = _time.monotonic()
        since = now - duration_seconds
        return self.replay(robot_id=robot_id, since=since)

    # ── rotation (灰犀牛 #5: 24h/文件) ─────────────────────────
    def needs_rotation(self, now: float) -> bool:
        if self._sink is None:
            return False
        return (now - self._current_shard_start) >= self.cfg.rotation_hours * 3600.0

    def rotate(self, now: float) -> str | None:
        """Close current shard, start a new one, prune old shards."""
        if self._sink is None or not self._sink.exists():
            self._current_shard_start = now
            return None
        shard_name = f"{self._base_name}_{int(now)}.jsonl"
        shard_path = self._shard_dir / shard_name
        self._sink.rename(shard_path)
        self._current_shard_start = now
        self._prune(now)
        return str(shard_path)

    def _prune(self, now: float) -> None:
        """Remove shards older than retention_days."""
        if self._shard_dir is None:
            return
        cutoff = now - self.cfg.retention_days * 86400.0
        for path in self._shard_dir.glob(f"{self._base_name}_*.jsonl"):
            try:
                ts = int(path.stem.rsplit("_", 1)[-1])
                if ts < cutoff:
                    path.unlink()
            except (ValueError, OSError):
                continue

    # ── disk health (Runbook 图6) ──────────────────────────────
    def disk_warning(self) -> bool:
        return self._disk_free_pct < self.cfg.disk_warn_pct

    def records(self) -> list[WormRecord]:
        return list(self._records)

    def _load_from_disk(self) -> None:
        """Restore hash chain from existing JSONL sink on startup.

        Without this, a restart breaks the chain: prev_hash resets to ""
        and new records cannot link to prior history (铁律三 violation).
        """
        if self._sink is None or not self._sink.exists():
            return
        try:
            with open(self._sink, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rec = WormRecord(**json.loads(line))
                    self._records.append(rec)
            if self._records:
                self._prev_hash = self._records[-1].hash
                self._current_shard_start = self._records[0].timestamp
        except (json.JSONDecodeError, TypeError, ValueError):
            # Corrupt sink — start fresh, old data is forensic evidence on disk
            pass

    def _persist(self, rec: WormRecord) -> None:
        if self._sink is None or self._sink_failed:
            return
        try:
            with open(self._sink, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(rec)) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except (OSError, PermissionError) as exc:
            ctx = {
                "sink": str(self._sink),
                "error": str(exc),
                "record_ts": rec.timestamp,
                "robot_id": rec.robot_id,
            }
            if self._mode == "DEMO":
                self._sink_failed = True
                rec.payload = dict(rec.payload, **{"worm_sink_fallback": True})
                import sys
                print(
                    f"[WORM] DEMO mode: sink failed, falling back to in-memory \u2014 {ctx}",
                    file=sys.stderr,
                )
                return
            raise RuntimeError(
                f"WORM sink write failed in {self._mode} mode: {ctx}"
            ) from exc
