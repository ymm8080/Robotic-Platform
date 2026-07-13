"""Type definitions for ZEWM_ROBCO_SRV OData integration.

Python 3.12+ uses StrEnum for string-backed enums.

Reference:
  SAP/ewm-cloud-robotics (Apache 2.0)
  d:/ewm robot/reference/design all/implementation plan/
"""

from __future__ import annotations

from enum import StrEnum


class RobotType(StrEnum):
    """SAP ZEWM_DE_ROBOT_TYPE domain values.

    Maps to /SCWM/TRSRC_TYP entries configured in SM30.
    """

    MIR = "MIR"
    KUKA = "KUKA"
    GEEKPLUS = "GEEKPLUS"
    HAIROBOTICS = "HAIROBOTICS"
    QUICKTRON = "QUICKTRON"


class ConfirmationStep(StrEnum):
    """Two-step warehouse task confirmation sentinel values.

    SAP EWM requires two separate OData calls to fully confirm
    a warehouse task: resource assignment (step 1) and
    quantity / bin / HU / exception code (step 2).
    """

    FIRST = "FIRST_CONF"
    SECOND = "SECOND_CONF"


class ExceptionCode(StrEnum):
    """SAP EWM exception codes for warehouse task confirmation.

    These map to /SCWM/DE_EXCCODE domain values. Robot errors
    are translated to these codes before calling confirm_task().
    """

    DAMAGED = "DAMG"  # Goods damaged (sensor failure, gripper fault)
    EMPTY = "EMPT"  # Source bin empty (short pick)
    WRONG_PRODUCT = "WRNG"  # Wrong product in bin
    QUANTITY_DIFF = "DIFF"  # Quantity difference vs expected
    BLOCKED = "BLKD"  # Bin or robot blocked (navigation, E-stop)


# ── Robot Error to SAP Exception Code Mapping ──────────────────────────
ROBOT_ERROR_TO_SAP_EXCCODE: dict[str, str] = {
    # Quicktron-specific errors
    "ERR_QT_LIDAR_ANOMALY:E001": ExceptionCode.DAMAGED,
    "ERR_QT_MOTOR_FAULT:E002": ExceptionCode.BLOCKED,
    "ERR_QT_BATTERY_LOW:E003": ExceptionCode.BLOCKED,
    "ERR_QT_OBSTACLE_DETECTED:E005": ExceptionCode.BLOCKED,
    "ERR_QT_NAVIGATION_FAILURE:E006": ExceptionCode.BLOCKED,
    "ERR_QT_EMERGENCY_STOP:E007": ExceptionCode.BLOCKED,
    "ERR_QT_BIN_MECHANISM_FAULT:E008": ExceptionCode.DAMAGED,
    # Platform-generated errors
    "ERR_SCS_TIMEOUT": ExceptionCode.BLOCKED,
    "ERR_TRAFFIC_VIOLATION": ExceptionCode.BLOCKED,
    "ERR_SENSOR_DEGRADED": ExceptionCode.DAMAGED,
}


def map_robot_error_to_exccode(error: str) -> str | None:
    """Map a robot error string to an SAP exception code.

    Args:
        error: Robot error string, e.g. ``"ERR_QT_MOTOR_FAULT:E002"``.

    Returns:
        The matching ``ExceptionCode`` value, or ``None`` if no mapping exists.
    """
    code = ROBOT_ERROR_TO_SAP_EXCCODE.get(error)
    if code is not None:
        return code
    if ":" in error:
        prefix = error.split(":", 1)[0]
        code = ROBOT_ERROR_TO_SAP_EXCCODE.get(prefix)
        if code is not None:
            return code
    return None
