"""WarehouseBackend ABC — contract for all warehouse backend implementations.

Mirrors the design of strategies/base.py. Each backend type (EWM, WM, etc.)
implements this ABC and is selected per warehouse via config.
"""

from abc import ABC, abstractmethod

from models.warehouse_task import WarehouseTask  # noqa: F401 — re-export


class WarehouseBackend(ABC):
    """Abstract base class for warehouse system backends.

    Each backend type (EWM OData, WM RFC, future: DB2 WMS, etc.) implements
    these methods. The factory selects the right backend per warehouse.

    Subclasses MUST set:
      backend_type_name = "unique-key"       # class-level, used by Registry
      display_name_str = "Human Readable"    # class-level display name
    """

    # ── Class-level identifiers (no instantiation needed) ──
    backend_type_name: str = ""  # Override in subclass
    display_name_str: str = ""  # Override in subclass

    @property
    def backend_type(self) -> str:
        """Unique backend type identifier, e.g. 'ewm', 'wm'."""
        return self.backend_type_name

    @property
    def display_name(self) -> str:
        """Human-readable name for logging/dashboard."""
        return self.display_name_str

    # ── Task CRUD ─────────────────────────────────────────

    @abstractmethod
    def list_tasks(
        self,
        warehouse: str,
        status: str = "0",
        top: int = 100,
        skip: int = 0,
    ) -> list[WarehouseTask]:
        """Fetch open warehouse tasks from the backend.

        Returns empty list on error (logged). Raises PermissionError on auth failure.
        """
        ...

    @abstractmethod
    def get_task(
        self,
        warehouse: str,
        task_id: str,
        item_no: str = "0001",
    ) -> WarehouseTask | None:
        """Get a single warehouse task by ID. Returns None if not found."""
        ...

    @abstractmethod
    def create_task(self, task: WarehouseTask) -> WarehouseTask | None:
        """Create a new warehouse task in the backend system.

        Returns updated task with external_id populated, or None on failure.
        """
        ...

    @abstractmethod
    def confirm_task(
        self,
        warehouse: str,
        task_id: str,
        qty: float,
        item_no: str = "0001",
    ) -> bool:
        """Confirm task completion in the backend system."""
        ...

    @abstractmethod
    def cancel_task(
        self,
        warehouse: str,
        task_id: str,
        item_no: str = "0001",
    ) -> bool:
        """Cancel a warehouse task."""
        ...

    # ── Health ────────────────────────────────────────────

    @abstractmethod
    def check_connection(self) -> dict:
        """Test connectivity and return status dict.

        Standard return schema:
            {
                "connected": bool,          # True if reachable
                "backend": str,             # backend_type value
                "mode": str,                # e.g. "rfc" | "http" | "odata"
                "warehouse_configured": bool, # True if config has necessary params
                "details": dict | None,     # Backend-specific extra info
            }
        On error: {"connected": False, "backend": str, "error": str, ...}
        """
        ...

    # ── Lifecycle ────────────────────────────────────────

    def close(self):
        """Release all backend connections (Redis, pyrfc, httpx, etc.).

        Called by Factory.reload() and __del__. Subclasses MUST call super().
        """
        pass

    # ── Optional ─────────────────────────────────────────

    def validate_config(self) -> list[str]:
        """Validate backend configuration. Return list of config error messages."""
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.backend_type}>"

    def __del__(self):
        self.close()
