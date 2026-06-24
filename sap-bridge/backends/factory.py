"""Warehouse backend factory — selects backend type per warehouse from config.

Usage:
    factory = WarehouseBackendFactory(config_dict)
    backend = factory.get_backend("WM01")
    tasks = backend.list_tasks("WM01")
"""

import logging
import os
from typing import Optional

import yaml

from .base import WarehouseBackend
from .registry import get_registry

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


class WarehouseBackendFactory:
    """Creates WarehouseBackend instances per warehouse from config.

    Config format (config.yaml):
        sap:
          warehouses:
            WM01:
              backend: ewm
              base_url: "http://sap-ewm:8000"
              client: "100"
              rate_limit: 80
            WM02:
              backend: wm
              rfc_ashost: "sap-wm.example.com"
              rfc_sysnr: "00"
              rfc_client: "800"
              rfc_lang: "ZH"
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self._config_path = config_path
        self._warehouses: dict[str, WarehouseBackend] = {}
        self._config: dict = {}
        self._registry = get_registry()
        self._load_config()

    def _load_config(self):
        """Load and parse warehouse config."""
        try:
            with open(self._config_path) as f:
                raw = yaml.safe_load(f)
            self._config = raw or {}
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self._config_path}")
            self._config = {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self._config = {}

    def get_backend(self, warehouse_id: str) -> Optional[WarehouseBackend]:
        """Get (or create) backend for a warehouse.

        Caches backend instances per warehouse — the same warehouse always
        returns the same backend object.
        """
        # Return cached instance
        if warehouse_id in self._warehouses:
            return self._warehouses[warehouse_id]

        # Look up warehouse config
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

    def get_warehouse_config(self, warehouse_id: str) -> Optional[dict]:
        """Get raw config dict for a warehouse."""
        warehouses = self._config.get("sap", {}).get("warehouses", {})
        return warehouses.get(warehouse_id)

    def reload(self):
        """Reload config from disk and clear cached backends."""
        self._warehouses.clear()
        self._load_config()

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

_factory: Optional[WarehouseBackendFactory] = None


def get_factory(config_path: str = DEFAULT_CONFIG_PATH) -> WarehouseBackendFactory:
    """Get the global backend factory singleton."""
    global _factory
    if _factory is None:
        _factory = WarehouseBackendFactory(config_path=config_path)
    return _factory


def get_backend_for(warehouse_id: str) -> Optional[WarehouseBackend]:
    """Convenience: get backend for a warehouse from the singleton factory."""
    return get_factory().get_backend(warehouse_id)
