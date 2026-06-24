"""WarehouseBackend ABC — contract for all warehouse backend implementations.

Mirrors the design of strategies/base.py. Each backend type (EWM, WM, etc.)
implements this ABC and is selected per warehouse via config.
"""

from abc import ABC, abstractmethod

from models.warehouse_task import WarehouseTask  # noqa: F401 — re-export for convenience


class WarehouseBackend(ABC):
    """Abstract base class for warehouse system backends.

    Each backend type (EWM OData, WM RFC, future: DB2 WMS, etc.) implements
    these methods. The factory selects the right backend per warehouse.
    """

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """Unique backend type identifier, e.g. 'ewm', 'wm'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for logging/dashboard, e.g. 'SAP EWM', 'SAP WM'."""
        ...

    # ── Task CRUD ─────────────────────────────────────────

    @abstractmethod
    def list_tasks(
        self, warehouse: str, status: str = "0",
        top: int = 100, skip: int = 0,
    ) -> list[WarehouseTask]:
        """Fetch open warehouse tasks from the backend."""
        ...

    @abstractmethod
    def get_task(
        self, warehouse: str, task_id: str, item_no: str = "0001",
    ) -> WarehouseTask | None:
        """Get a single warehouse task by ID."""
        ...

    @abstractmethod
    def create_task(self, task: WarehouseTask) -> WarehouseTask | None:
        """Create a new warehouse task in the backend system."""
        ...

    @abstractmethod
    def confirm_task(
        self, warehouse: str, task_id: str, qty: float,
        item_no: str = "0001",
    ) -> bool:
        """Confirm task completion in the backend system."""
        ...

    @abstractmethod
    def cancel_task(
        self, warehouse: str, task_id: str, item_no: str = "0001",
    ) -> bool:
        """Cancel a warehouse task."""
        ...

    # ── Health ────────────────────────────────────────────

    @abstractmethod
    def check_connection(self) -> dict:
        """Test connectivity and return status dict.

        Returns:
            {"connected": bool, "status_code": int | None, "error": str | None}
        """
        ...

    # ── Optional overrides ────────────────────────────────

    def validate_config(self) -> list[str]:
        """Validate backend configuration. Return list of config error messages."""
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.backend_type}>"
