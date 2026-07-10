"""Module entry point: ``python -m traffic_coordinator_v5.simulator``."""

from __future__ import annotations

import sys

from traffic_coordinator_v5.simulator.cli import run

if __name__ == "__main__":
    sys.exit(run())
