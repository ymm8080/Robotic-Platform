"""Map transformer — per-brand bridge between native maps and the unified lane graph.

Open-RMF pattern: each fleet adapter loads the same NAV_GRAPH but must align
its robot's coordinate frame via ``reference_coordinates``. v5.0 makes that
contract explicit through ``MapTransformer``:

- ``native_to_unified_pose`` converts vendor (x, y, theta) to the platform's
  common frame.
- ``unified_to_native_goal`` converts a unified lane/node goal into a native
  navigation target the SCS can execute.
- ``native_to_unified_lane`` maps a vendor-reported current node / zone to a
  unified lane id for ingestion.

A default identity transformer is provided for fleets that already speak the
unified frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.messages import Pose


@dataclass
class MapTransformer:
    """Coordinate + lane mapping for one robot brand."""

    brand: str
    native_to_unified_pose: Callable[[float, float, float], Pose]
    unified_to_native_goal: Callable[[str], dict]
    native_to_unified_lane: Callable[[str], str | None]

    @classmethod
    def identity(cls, brand: str) -> "MapTransformer":
        """No-op transformer for fleets already operating in the unified frame."""
        return cls(
            brand=brand,
            native_to_unified_pose=lambda x, y, theta: Pose(x=x, y=y, theta=theta),
            unified_to_native_goal=lambda lane_id: {"lane_id": lane_id},
            native_to_unified_lane=lambda lane_id: lane_id,
        )

    def transform_pose(self, x: float, y: float, theta: float) -> Pose:
        return self.native_to_unified_pose(x, y, theta)

    def transform_goal(self, lane_id: str) -> dict:
        return self.unified_to_native_goal(lane_id)

    def transform_lane(self, native_lane: str) -> str | None:
        return self.native_to_unified_lane(native_lane)
