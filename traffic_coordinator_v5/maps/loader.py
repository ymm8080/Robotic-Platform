"""Facility map YAML loader.

Parses a v5.0 facility_map.yaml into a ``FixedLaneMap`` plus registration
lists for intersections, chargers, and lifts.  The caller (traffic coordinator
main or bootstrap) feeds these into the ``RobotPlatformCoordinator``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.messages import EnvConstraints
from core.platform.fixed_lane_map import FixedLaneMap, Lane, SpeedClass


@dataclass
class FacilityMap:
    """Result of loading a facility_map.yaml."""

    fmap: FixedLaneMap = field(default_factory=FixedLaneMap)
    intersections: list[str] = field(default_factory=list)
    charger_ids: list[str] = field(default_factory=list)
    lift_ids: list[dict[str, Any]] = field(default_factory=list)
    facility_name: str = ""
    warnings: list[str] = field(default_factory=list)


def _parse_env(raw: dict | None) -> EnvConstraints:
    """Parse optional env constraints from YAML."""
    if raw is None:
        return EnvConstraints()
    return EnvConstraints(
        max_grade=float(raw.get("max_grade", 0.0)),
        floor_threshold=float(raw.get("floor_threshold", 0.0)),
        min_friction=float(raw.get("min_friction", 0.0)),
    )


def _parse_speed_class(raw: str | None) -> SpeedClass:
    """Parse speed class string into enum."""
    if raw is None:
        return SpeedClass.FAST
    try:
        return SpeedClass(raw.upper())
    except ValueError:
        return SpeedClass.FAST


def load_facility_map(path: str | Path | None = None) -> FacilityMap:
    """Load a facility map from a YAML file.

    If *path* is None, the default ``facility_map.yaml`` next to this module
    is used.
    """
    path = Path(__file__).resolve().parent / "facility_map.yaml" if path is None else Path(path)

    if not path.is_file():
        return FacilityMap(warnings=[f"map file not found: {path}"])

    with open(path, encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    result = FacilityMap()
    result.facility_name = (
        raw.get("facility", {}).get("name", "")
        or raw.get("facility", {}).get("name", "")
        or path.stem
    )

    # ── parse lanes ───────────────────────────────────────────────
    for entry in raw.get("lanes", []) or []:
        try:
            lane = Lane(
                lane_id=str(entry["lane_id"]),
                from_node=str(entry["from_node"]),
                to_node=str(entry["to_node"]),
                length=float(entry.get("length", 10.0)),
                width=float(entry.get("width", 1.2)),
                speed_class=_parse_speed_class(entry.get("speed_class")),
                allowed_models=[str(m) for m in entry.get("allowed_models", []) or []],
                max_speed=float(entry.get("max_speed", 1.5)),
                env=_parse_env(entry.get("env")),
                no_reverse=bool(entry.get("no_reverse", False)),
                charger=bool(entry.get("charger", False)),
                lift_id=str(entry["lift_id"]) if entry.get("lift_id") else None,
                floor=int(entry["floor"]) if entry.get("floor") is not None else None,
                intersection_id=str(entry["intersection_id"])
                if entry.get("intersection_id")
                else None,
                direction=int(entry.get("direction", 0)),
            )
            result.fmap.add_lane(lane)
        except (KeyError, ValueError, TypeError) as exc:
            result.warnings.append(f"skipping lane {entry.get('lane_id', entry)}: {exc}")

    # ── parse intersections ───────────────────────────────────────
    for entry in raw.get("intersections", []) or []:
        try:
            iid = str(entry["id"])
            result.intersections.append(iid)
        except (KeyError, TypeError) as exc:
            result.warnings.append(f"skipping intersection {entry}: {exc}")

    # ── parse chargers ────────────────────────────────────────────
    for entry in raw.get("chargers", []) or []:
        try:
            cid = str(entry["id"])
            result.charger_ids.append(cid)
        except (KeyError, TypeError) as exc:
            result.warnings.append(f"skipping charger {entry}: {exc}")

    # ── parse lifts ───────────────────────────────────────────────
    for entry in raw.get("lifts", []) or []:
        try:
            result.lift_ids.append(
                {
                    "id": str(entry["id"]),
                    "lanes": [str(l) for l in entry.get("lanes", []) or []],
                    "floors": [int(f) for f in entry.get("floors", []) or []],
                }
            )
        except (KeyError, TypeError) as exc:
            result.warnings.append(f"skipping lift {entry}: {exc}")

    # ── validate map integrity ────────────────────────────────────
    map_warnings = result.fmap.validate()
    result.warnings.extend(map_warnings)

    return result
