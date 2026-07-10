"""Lightweight observability for the v5.0 core.

A minimal in-memory metrics registry.  In production this is exported to
Prometheus / OpenTelemetry by the gateway; the coordinator only updates
counters and gauges.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetricsSnapshot:
    uplinks: int = 0
    orders_submitted: int = 0
    tasks_allocated: int = 0
    tasks_completed: int = 0
    tasks_requeued: int = 0
    collision_holds: int = 0
    deadlocks: int = 0
    adapter_parse_errors: int = 0
    worm_records: int = 0


class CoreMetrics:
    """In-memory metrics for the core platform loop."""

    def __init__(self) -> None:
        self._snap = MetricsSnapshot()

    def inc(self, name: str, delta: int = 1) -> None:
        if not hasattr(self._snap, name):
            raise AttributeError(f"unknown metric {name}")
        current = getattr(self._snap, name)
        setattr(self._snap, name, current + delta)

    def snapshot(self) -> MetricsSnapshot:
        """Return a copy of current metrics (cheap; useful for dashboards)."""
        from dataclasses import replace
        return replace(self._snap)

    def reset(self) -> None:
        self._snap = MetricsSnapshot()
