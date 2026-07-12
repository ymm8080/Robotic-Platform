"""Shared test configuration for core tests.

Forces DEMO mode to avoid /data/worm permission issues in CI.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import CoreConfig

_original_init = CoreConfig.__init__


def _patched_init(self, *args, **kwargs):
    """Override CoreConfig.__init__ to default to DEMO mode.

    In CI (GitHub Actions, ubuntu-latest), /data is not writable.
    DEMO mode skips the PRODUCTION-only WORM disk writability check.
    Tests that explicitly pass mode='PRODUCTION' are not affected.
    """
    if "mode" not in kwargs:
        kwargs["mode"] = "DEMO"
    _original_init(self, *args, **kwargs)


@pytest.fixture(autouse=True)
def _force_demo_mode():
    """Auto-applied fixture: default CoreConfig to DEMO mode for all core tests."""
    with patch.object(CoreConfig, "__init__", _patched_init):
        yield
