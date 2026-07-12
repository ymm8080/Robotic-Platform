"""Clients for external services.

Service clients:
  - ZewmRobcoClient — HTTP client for SAP ZEWM_ROBCO_SRV OData
  - TrafficCoordinatorClient — HTTP client for Traffic Coordinator REST API

Type definitions and exceptions:
  - RobotType, ExceptionCode, ConfirmationStep, map_robot_error_to_exccode
  - RobcoError hierarchy (17 exception classes)
  - raise_for_error_code()
"""

from __future__ import annotations

<<<<<<< HEAD
from .traffic_coordinator_client import TrafficCoordinatorClient
=======
from .traffic_coordinator_client import ClientResult, TrafficCoordinatorClient
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
from .zewm_robco_client import ZewmRobcoClient
from .zewm_robco_exceptions import (
    NoErrorQueueError,
    NoOrderFoundError,
    NoRobotResourceTypeError,
    QueueNotChangedError,
    RobcoError,
    RobcoInternalError,
    RobotHasOrderError,
    RobotNotFoundError,
    StatusNotSetError,
    WarehouseOrderLockedError,
    WhoAssignedError,
    WhoInProcessError,
    WhoLockedError,
    WhoNotFoundError,
    WhoNotUnassignedError,
    WhtAlreadyConfirmedError,
    WhtAssignedError,
    WhtNotConfirmedError,
    raise_for_error_code,
)
from .zewm_robco_types import (
    ConfirmationStep,
    ExceptionCode,
    RobotType,
    map_robot_error_to_exccode,
)

__all__ = [
    # Clients
    "TrafficCoordinatorClient",
<<<<<<< HEAD
=======
    "ClientResult",
>>>>>>> cc689e2268ba4a3d37c8aff7f99fb9dd46e122da
    "ZewmRobcoClient",
    # Types
    "RobotType",
    "ConfirmationStep",
    "ExceptionCode",
    "map_robot_error_to_exccode",
    # Exceptions
    "RobcoError",
    "RobotNotFoundError",
    "RobotHasOrderError",
    "StatusNotSetError",
    "NoRobotResourceTypeError",
    "WhoNotFoundError",
    "WhoLockedError",
    "WhoAssignedError",
    "WhoInProcessError",
    "WhoNotUnassignedError",
    "NoOrderFoundError",
    "WarehouseOrderLockedError",
    "WhtAssignedError",
    "WhtNotConfirmedError",
    "WhtAlreadyConfirmedError",
    "NoErrorQueueError",
    "QueueNotChangedError",
    "RobcoInternalError",
    "raise_for_error_code",
]
