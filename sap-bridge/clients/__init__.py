"""Clients for external services.

Service clients:
  - TrafficCoordinatorClient - HTTP client for Traffic Coordinator REST API
"""

from __future__ import annotations

from .traffic_coordinator_client import ClientResult, TrafficCoordinatorClient

__all__ = [
    "TrafficCoordinatorClient",
    "ClientResult",
]
