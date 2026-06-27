"""Warehouse backend implementations.

Plugin registry pattern mirroring strategies/. Each backend implements the
WarehouseBackend ABC and is registered by type name. The factory selects
the correct backend per warehouse based on config.yaml.
"""

from .base import WarehouseBackend, WarehouseTask
from .ewm_backend import EwmBackend
from .registry import BackendRegistry, get_registry
from .wm_backend import WmBackend

__all__ = [
    "WarehouseBackend",
    "WarehouseTask",
    "BackendRegistry",
    "get_registry",
    "EwmBackend",
    "WmBackend",
]
