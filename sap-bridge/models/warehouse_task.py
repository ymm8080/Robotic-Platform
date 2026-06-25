"""Canonical warehouse task model — normalized for both SAP EWM and Classic WM.

Only truly cross-system fields are top-level. Backend-specific data goes
into the vendor_data dict. This keeps the model lean and avoids field
proliferation as new backends are added.
"""

from dataclasses import dataclass, field


@dataclass
class WarehouseTask:
    """Normalized warehouse task representing either an EWM Warehouse Task or WM Transfer Order.

    Core fields are shared by all backends. Backend-specific enrichment
    (EWM: process_type, HU info; WM: transfer_type, movement_type, etc.)
    lives in vendor_data.
    """

    # ── Core fields (every backend must populate) ──────────
    source_system: str                    # "EWM" | "WM"
    warehouse: str                        # Warehouse number
    external_id: str                      # WT number (EWM) or TO number (WM)
    item_no: str = "0001"                 # Item number within the task
    task_type: str = "MOVE"               # PICK | PUT | MOVE | CHARGE (normalized)
    source_bin: str | None = None
    dest_bin: str | None = None
    product: str | None = None
    batch: str | None = None
    target_qty: float = 0.0
    actual_qty: float = 0.0
    uom: str = "EA"
    status: str = "0"                     # 0=Open, 1=InProcess, 2=Confirmed, 3=Cancelled

    # ── Vendor-specific data ──────────────────────────────
    vendor_data: dict = field(default_factory=dict)

    @property
    def is_ewm(self) -> bool:
        return self.source_system.upper() == "EWM"

    @property
    def is_wm(self) -> bool:
        return self.source_system.upper() == "WM"

    # ── Convenience property accessors ────────────────────
    # These provide backward-compatible access to common vendor fields.

    @property
    def process_type(self) -> str | None:
        """EWM process type (e.g. PICK, PUT, STO)."""
        return self.vendor_data.get("process_type")

    @property
    def warehouse_order(self) -> str | None:
        """EWM Warehouse Order number."""
        return self.vendor_data.get("warehouse_order")

    @property
    def is_hu_task(self) -> bool:
        """EWM: whether this is a Handling Unit task."""
        return bool(self.vendor_data.get("is_hu_task", False))

    @property
    def source_hu(self) -> str | None:
        return self.vendor_data.get("source_hu")

    @property
    def dest_hu(self) -> str | None:
        return self.vendor_data.get("dest_hu")

    @property
    def to_number(self) -> str | None:
        """WM Transfer Order number (same as external_id)."""
        return self.vendor_data.get("to_number")

    @to_number.setter
    def to_number(self, value: str):
        self.vendor_data["to_number"] = value

    @property
    def movement_type(self) -> str | None:
        """WM BWLVS movement type."""
        return self.vendor_data.get("movement_type")

    @movement_type.setter
    def movement_type(self, value: str):
        self.vendor_data["movement_type"] = value

    @property
    def transfer_type(self) -> str | None:
        """WM transfer type (E=putaway, A=removal, U=transfer)."""
        return self.vendor_data.get("transfer_type")

    @transfer_type.setter
    def transfer_type(self, value: str):
        self.vendor_data["transfer_type"] = value

    @property
    def plant(self) -> str | None:
        return self.vendor_data.get("plant")

    @plant.setter
    def plant(self, value: str):
        self.vendor_data["plant"] = value

    @property
    def storage_location(self) -> str | None:
        return self.vendor_data.get("storage_location")

    @storage_location.setter
    def storage_location(self, value: str):
        self.vendor_data["storage_location"] = value

    @property
    def raw(self) -> dict:
        """Raw payload from backend, for debugging."""
        return self.vendor_data.get("raw", {})

    def to_dict(self) -> dict:
        return {
            "sourceSystem": self.source_system,
            "warehouse": self.warehouse,
            "externalId": self.external_id,
            "itemNo": self.item_no,
            "taskType": self.task_type,
            "sourceBin": self.source_bin,
            "destBin": self.dest_bin,
            "product": self.product,
            "batch": self.batch,
            "targetQty": self.target_qty,
            "actualQty": self.actual_qty,
            "uom": self.uom,
            "status": self.status,
        }
