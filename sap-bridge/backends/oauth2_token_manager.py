"""Re-exports from sap-bridge/auth.py — kept for backwards compatibility."""
from auth import OAuth2TokenManager, read_client_secret  # noqa: F401

__all__ = ["OAuth2TokenManager", "read_client_secret"]
