"""Warehouse backend factory — selects backend type per warehouse from config.

Usage:
    factory = WarehouseBackendFactory(config_dict)
    backend = factory.get_backend("WM02")
    tasks = backend.list_tasks("WM02")

Thread-safe: get_backend() uses a lock to prevent double-init race.
"""

import logging
import os
import re
import threading

import yaml

from .base import WarehouseBackend
from .registry import get_registry

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

# Expand shell-style ${VAR:-default} and ${VAR} placeholders in config values.
_ENV_PLACEHOLDER = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-?(?P<default>[^}]*))?\}")


def _expand_env_vars(obj):
    """Recursively expand ${VAR:-default} placeholders in strings within dicts/lists."""
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(v) for v in obj]
    if isinstance(obj, str):
        def _repl(match):
            return os.environ.get(match.group("name"), match.group("default") or "")
        return _ENV_PLACEHOLDER.sub(_repl, obj)
    return obj


class WarehouseBackendFactory:
    """Creates WarehouseBackend instances per warehouse from config.

    Config format (config.yaml):
        sap:
          warehouses:
            WM01:
              backend: ewm
              base_url: "http://sap-ewm:8000"
              client: "100"
            WM02:
              backend: wm
              mode: http
              simulator_url: "http://wm-simulator:8001"
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self._config_path = config_path
        self._warehouses: dict[str, WarehouseBackend] = {}
        self._config: dict = {}
        self._registry = get_registry()
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self):
        """Load, parse, and expand environment variables in warehouse config."""
        try:
            with open(self._config_path) as f:
                raw = yaml.safe_load(f)
            self._config = _expand_env_vars(raw or {})
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self._config_path}")
            self._config = {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self._config = {}

    def get_backend(self, warehouse_id: str) -> WarehouseBackend | None:
        """Get (or create) backend for a warehouse.

        Thread-safe with per-instance lock. Caches backend instances.
        """
        # Fast path (read-only, no lock)
        cached = self._warehouses.get(warehouse_id)
        if cached is not None:
            return cached

        with self._lock:
            # Double-check after acquiring lock
            cached = self._warehouses.get(warehouse_id)
            if cached is not None:
                return cached

            warehouses = self._config.get("sap", {}).get("warehouses", {})
            wh_config = warehouses.get(warehouse_id)

            if wh_config is None:
                logger.warning(f"No config for warehouse '{warehouse_id}'")
                return None

            backend_type = wh_config.get("backend", "ewm")
            backend = self._registry.instantiate(backend_type, wh_config)
            if backend is None:
                logger.error(
                    f"Failed to create backend '{backend_type}' "
                    f"for warehouse '{warehouse_id}'"
                )
                return None

            self._warehouses[warehouse_id] = backend
            logger.info(
                f"Warehouse '{warehouse_id}' → {backend.display_name} "
                f"(type={backend_type})"
            )
            return backend

    def list_warehouses(self) -> list[str]:
        """List all configured warehouse IDs."""
        warehouses = self._config.get("sap", {}).get("warehouses", {})
        return list(warehouses.keys())

    def get_warehouse_config(self, warehouse_id: str) -> dict | None:
        """Get raw config dict for a warehouse."""
        warehouses = self._config.get("sap", {}).get("warehouses", {})
        return warehouses.get(warehouse_id)

    def reload(self):
        """Reload config from disk and recreate all backends.

        Calls close() on each backend before discarding.
        """
        with self._lock:
            for wh_id, backend in self._warehouses.items():
                try:
                    backend.close()
                    logger.debug(f"Closed backend for warehouse '{wh_id}'")
                except Exception as e:
                    logger.warning(f"Error closing backend for '{wh_id}': {e}")
            self._warehouses.clear()
            self._load_config()
        logger.info("Factory reloaded — all backends recreated on next access")

    def health_check_all(self) -> dict[str, dict]:
        """Check connectivity for all configured warehouses."""
        results = {}
        for wh_id in self.list_warehouses():
            backend = self.get_backend(wh_id)
            if backend:
                results[wh_id] = backend.check_connection()
            else:
                results[wh_id] = {"connected": False, "error": "no_backend"}
        return results


# ── Module-level singleton ─────────────────────────────────

_factory: WarehouseBackendFactory | None = None
_factory_lock = threading.Lock()


def get_factory(config_path: str | None = None) -> WarehouseBackendFactory:
    """Get the global backend factory singleton.

    Uses DEFAULT_CONFIG_PATH on first call. Pass config_path to initialize
    with a custom path. Thread-safe.
    """
    global _factory
    if _factory is None:
        with _factory_lock:
            if _factory is None:
                _factory = WarehouseBackendFactory(config_path=config_path or DEFAULT_CONFIG_PATH)
    elif config_path is not None and config_path != _factory._config_path:
        logger.warning(
            f"get_factory() called with config_path={config_path!r} "
            f"but factory already initialized with {_factory._config_path!r}. "
            f"Call factory.reload() to reload config."
        )
    return _factory


def get_backend_for(warehouse_id: str) -> WarehouseBackend | None:
    """Convenience: get backend for a warehouse from the singleton factory."""
    return get_factory().get_backend(warehouse_id)
