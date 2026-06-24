"""Canonical warehouse task model — normalized for both SAP EWM and Classic WM."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WarehouseTask:
    """Normalized warehouse task representing either an EWM Warehouse Task or WM Transfer Order.

    The model normalizes the two SAP warehouse concepts into one canonical shape.
    Use source_system to distinguish which backend produced it.
    """

    # ── Canonical fields (populated for both EWM and WM) ──
    source_system: str                    # "EWM" | "WM"
    warehouse: str                        # Warehouse number (EWM: 4-char, WM: 3-char)
    external_id: str                      # WT number (EWM) or TO number (WM)
    item_no: str = "0001"                 # Item number within the task/order
    task_type: str = "MOVE"               # PICK | PUT | MOVE | CHARGE (normalized)
    source_bin: Optional[str] = None
    dest_bin: Optional[str] = None
    product: Optional[str] = None
    batch: Optional[str] = None
    target_qty: float = 0.0
    actual_qty: float = 0.0
    uom: str = "EA"
    status: str = "0"                     # 0=Open, 1=InProcess, 2=Confirmed, 3=Cancelled

    # ── EWM-specific ──
    warehouse_order: Optional[str] = None  # Warehouse Order number
    process_type: Optional[str] = None     # e.g. "PICK", "PUT", "STO"
    is_hu_task: bool = False
    source_hu: Optional[str] = None
    dest_hu: Optional[str] = None

    # ── WM-specific ──
    to_number: Optional[str] = None        # WM Transfer Order number (same as external_id)
    movement_type: Optional[str] = None    # BWLVS movement type
    transfer_type: Optional[str] = None    # E=putaway, A=removal, U=transfer
    storage_unit: Optional[str] = None     # Storage Unit number
    plant: Optional[str] = None
    storage_location: Optional[str] = None

    # ── Raw payload for debugging ──
    raw: dict = field(default_factory=dict)

    @property
    def is_ewm(self) -> bool:
        return self.source_system.upper() == "EWM"

    @property
    def is_wm(self) -> bool:
        return self.source_system.upper() == "WM"

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
            "warehouseOrder": self.warehouse_order,
            "processType": self.process_type,
            "isHuTask": self.is_hu_task,
            "sourceHu": self.source_hu,
            "destHu": self.dest_hu,
            "toNumber": self.to_number,
            "movementType": self.movement_type,
            "transferType": self.transfer_type,
            "storageUnit": self.storage_unit,
            "plant": self.plant,
            "storageLocation": self.storage_location,
        }
