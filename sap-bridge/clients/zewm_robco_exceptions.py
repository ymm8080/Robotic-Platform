"""Exception hierarchy for ZEWM_ROBCO_SRV OData errors.

17 exception classes matching all SAP error codes from the ABAP function
modules and the SAP Python reference client.

Usage::
    from clients.zewm_robco_exceptions import (
        RobcoError, RobotNotFoundError, raise_for_error_code,
    )

    try:
        ...
    except RobcoError as exc:
        ...

    raise_for_error_code("ROBOT_NOT_FOUND", "Robot MIR_001 not found")
"""

from __future__ import annotations


class RobcoError(Exception):
    """Base exception for all ZEWM ROBCO errors."""

    error_code: str = "ROBCO_ERROR"

    def __init__(self, message: str = ""):
        msg = message or self.error_code
        super().__init__(msg)


# ── Robot errors ───────────────────────────────────────────────────────


class RobotNotFoundError(RobcoError):
    """Requested robot resource does not exist in SAP EWM."""

    error_code = "ROBOT_NOT_FOUND"


class RobotHasOrderError(RobcoError):
    """Robot already has a warehouse order assigned."""

    error_code = "ROBOT_HAS_ORDER"


class StatusNotSetError(RobcoError):
    """Failed to set robot status in SAP EWM."""

    error_code = "ROBOT_STATUS_NOT_SET"


class NoRobotResourceTypeError(RobcoError):
    """No robot resource type configured for the given parameters."""

    error_code = "NO_ROBOT_RESOURCE_TYPE"


# ── Warehouse Order (WHO) errors ───────────────────────────────────────


class WhoNotFoundError(RobcoError):
    """Warehouse order does not exist."""

    error_code = "WHO_NOT_FOUND"


class WhoLockedError(RobcoError):
    """Warehouse order is locked by another process."""

    error_code = "WHO_LOCKED"


class WhoAssignedError(RobcoError):
    """Warehouse order is already assigned to a resource."""

    error_code = "WHO_ASSIGNED"


class WhoInProcessError(RobcoError):
    """Warehouse order is currently in process."""

    error_code = "WHO_IN_PROCESS"


class WhoNotUnassignedError(RobcoError):
    """Warehouse order could not be unassigned from its resource."""

    error_code = "WHO_NOT_UNASSIGNED"


class NoOrderFoundError(RobcoError):
    """No warehouse orders found matching the criteria."""

    error_code = "NO_ORDER_FOUND"


class WarehouseOrderLockedError(RobcoError):
    """Warehouse order is locked by another transaction."""

    error_code = "WAREHOUSE_ORDER_LOCKED"


# ── Warehouse Task (WHT) errors ────────────────────────────────────────


class WhtAssignedError(RobcoError):
    """Warehouse task is already assigned to a resource."""

    error_code = "WHT_ASSIGNED"


class WhtNotConfirmedError(RobcoError):
    """Warehouse task could not be confirmed."""

    error_code = "WHT_NOT_CONFIRMED"


class WhtAlreadyConfirmedError(RobcoError):
    """Warehouse task has already been confirmed."""

    error_code = "WHT_ALREADY_CONFIRMED"


# ── Error queue errors ─────────────────────────────────────────────────


class NoErrorQueueError(RobcoError):
    """No error queue exists for the given resource or warehouse."""

    error_code = "NO_ERROR_QUEUE"


class QueueNotChangedError(RobcoError):
    """Error queue status could not be changed."""

    error_code = "QUEUE_NOT_CHANGED"


# ── Internal errors ────────────────────────────────────────────────────


class RobcoInternalError(RobcoError):
    """Unexpected internal error in ZEWM_ROBCO_SRV."""

    error_code = "INTERNAL_ERROR"


# ── Error Code → Exception Mapping ─────────────────────────────────────

_ERROR_CODE_MAP: dict[str, type[RobcoError]] = {
    "ROBOT_NOT_FOUND": RobotNotFoundError,
    "ROBOT_HAS_ORDER": RobotHasOrderError,
    "ROBOT_STATUS_NOT_SET": StatusNotSetError,
    "NO_ROBOT_RESOURCE_TYPE": NoRobotResourceTypeError,
    "WHO_NOT_FOUND": WhoNotFoundError,
    "WHO_LOCKED": WhoLockedError,
    "WHO_ASSIGNED": WhoAssignedError,
    "WHO_IN_PROCESS": WhoInProcessError,
    "WHO_NOT_UNASSIGNED": WhoNotUnassignedError,
    "NO_ORDER_FOUND": NoOrderFoundError,
    "WAREHOUSE_ORDER_LOCKED": WarehouseOrderLockedError,
    "WHT_ASSIGNED": WhtAssignedError,
    "WHT_NOT_CONFIRMED": WhtNotConfirmedError,
    "WHT_ALREADY_CONFIRMED": WhtAlreadyConfirmedError,
    "NO_ERROR_QUEUE": NoErrorQueueError,
    "QUEUE_NOT_CHANGED": QueueNotChangedError,
    "INTERNAL_ERROR": RobcoInternalError,
    "INTERNAL_SERVER_ERROR": RobcoInternalError,
}


def raise_for_error_code(error_code: str, detail: str = "") -> None:
    """Raise the appropriate exception class for an SAP error code.

    Args:
        error_code: SAP error code string, e.g. ``"ROBOT_NOT_FOUND"``.
        detail: Optional human-readable detail message.

    Raises:
        The matching ``RobcoError`` subclass, or ``RobcoError`` itself
        if the error code is unknown.
    """
    exc_cls = _ERROR_CODE_MAP.get(error_code, RobcoError)
    msg = f"[{error_code}]" if not detail else f"[{error_code}] {detail}"
    raise exc_cls(msg)
