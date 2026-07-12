"""Pytest configuration for core tests.

Forces WORM sink to a temp directory so tests don't fail in CI
environments where /data/worm doesn't exist.
"""
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _temp_worm_sink(monkeypatch):
    """Redirect WORM sink to a temp dir for all core tests.

    The default WormConfig.sink_dir is /data/worm which doesn't exist
    in CI. This fixture patches the default to a temp directory so
    PRODUCTION-mode tests that create CoreConfig() directly don't
    crash on WORM writes.
    """
    tmp = tempfile.mkdtemp(prefix="worm-test-")
    monkeypatch.setattr("core.config.WormConfig.sink_dir", tmp)
    yield
