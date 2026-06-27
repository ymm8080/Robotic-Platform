"""Shared test fixtures and configuration."""
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Test configuration overrides
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("REDIS_URL_TEST", "redis://localhost:6379/15")
os.environ.setdefault("DB_PATH", "/tmp/test_robot_platform.db")
