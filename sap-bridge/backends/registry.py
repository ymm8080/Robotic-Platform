"""Warehouse backend registry — singleton holding all registered backend types.

Mirrors the design of strategies/registry.py. Backends are registered by type
name and instantiated per warehouse via the factory.
"""

import logging

from .base import WarehouseBackend
from .ewm_backend import EwmBackend
from .wm_backend import WmBackend

logger = logging.getLogger(__name__)


class BackendRegistry:
    """Registry of warehouse backend implementations.

    Backend types are registered by name (e.g. "ewm", "wm").
    The factory selects one per warehouse based on config.
    """

    def __init__(self):
        self._backends: dict[str, type[WarehouseBackend]] = {}
        self._register_builtin()

    def _register_builtin(self):
        """Register all built-in backend types."""
        for cls in [EwmBackend, WmBackend]:
            # Instantiate once to get the type name, then store the class
            instance = cls()
            self._backends[instance.backend_type.lower()] = cls
            logger.info(f"Registered backend type: {instance.backend_type} ({cls.__name__})")

    def register(self, backend_cls: type[WarehouseBackend]):
        """Register a custom backend class (for testing or plugins)."""
        # Instantiate to verify it works and get type name
        instance = backend_cls()
        key = instance.backend_type.lower()
        self._backends[key] = backend_cls
        logger.info(f"Registered custom backend: {key} ({backend_cls.__name__})")

    def get_class(self, backend_type: str) -> type[WarehouseBackend] | None:
        """Get backend class by type name. Case-insensitive."""
        return self._backends.get(backend_type.lower())

    def instantiate(self, backend_type: str, config: dict) -> WarehouseBackend | None:
        """Create a backend instance for the given type with config."""
        cls = self.get_class(backend_type)
        if cls is None:
            logger.error(f"No backend registered for type '{backend_type}'")
            return None
        try:
            return cls(config=config)
        except Exception as e:
            logger.error(f"Failed to instantiate backend '{backend_type}': {e}")
            return None

    def list_types(self) -> list[str]:
        """List all registered backend type names."""
        return sorted(self._backends.keys())

    def count(self) -> int:
        return len(self._backends)

    def __repr__(self) -> str:
        return f"<BackendRegistry types={self.list_types()}>"


# ── Singleton ──────────────────────────────────────────────

_registry: BackendRegistry | None = None


def get_registry() -> BackendRegistry:
    """Get the global backend registry singleton."""
    global _registry
    if _registry is None:
        _registry = BackendRegistry()
    return _registry
