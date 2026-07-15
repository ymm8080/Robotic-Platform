"""LaneGraph wrapper around ``core.platform.fixed_lane_map.FixedLaneMap``."""

from __future__ import annotations

import math
import threading
from collections import deque
from pathlib import Path
from typing import Any

from core.platform.fixed_lane_map import FixedLaneMap, Lane
from traffic_coordinator_v5.maps.loader import load_facility_map

# Module-level cache: (frozenset of lane_ids) → positions dict.
# This prevents recomputing BFS positions when multiple LaneGraph instances
# are created from the same underlying FixedLaneMap (e.g. in tests or when
# the simulator and coordinator both load the same facility map).
# A max size prevents unbounded memory growth in dynamic map-loading scenarios.
_BFS_POSITIONS_CACHE: dict[frozenset[str], dict[str, tuple[float, float]]] = {}
_BFS_POSITIONS_CACHE_MAX = 32
_BFS_POSITIONS_CACHE_LOCK = threading.Lock()


class LaneGraph:
    """Lightweight, simulator-friendly view of the facility lane graph.

    Wraps ``FixedLaneMap`` and exposes lane geometry, connectivity, and a
    deterministic node layout for simulators that do not require real-world
    coordinates.
    """

    # Metres between disconnected components in the BFS layout.
    COMPONENT_SPACING = 50.0

    def __init__(
        self, fmap: FixedLaneMap, node_positions: dict[str, tuple[float, float]] | None = None
    ) -> None:
        self._fmap = fmap
        self._positions = node_positions or {}
        if not self._positions and fmap.all_lanes():
            # Cache key: frozenset of lane IDs — deterministic for a given map.
            cache_key = frozenset(l.lane_id for l in fmap.all_lanes())
            with _BFS_POSITIONS_CACHE_LOCK:
                cached = _BFS_POSITIONS_CACHE.get(cache_key)
                if cached is not None:
                    self._positions = dict(cached)  # defensive copy
                else:
                    self._positions = self._compute_bfs_positions()
                    # Enforce max cache size to prevent unbounded growth.
                    if len(_BFS_POSITIONS_CACHE) >= _BFS_POSITIONS_CACHE_MAX:
                        _BFS_POSITIONS_CACHE.pop(next(iter(_BFS_POSITIONS_CACHE)))
                    _BFS_POSITIONS_CACHE[cache_key] = dict(self._positions)

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> LaneGraph:
        """Load a lane graph from a facility_map.yaml file."""
        facility = load_facility_map(path)
        positions: dict[str, tuple[float, float]] = {}
        if path is not None:
            positions = cls._load_yaml_positions(path)
        return cls(facility.fmap, positions)

    @staticmethod
    def _load_yaml_positions(path: str | Path) -> dict[str, tuple[float, float]]:
        """Read explicit (x, y) coordinates from the YAML nodes block."""
        import yaml

        positions: dict[str, tuple[float, float]] = {}
        with open(path, encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}
        for node in raw.get("nodes", []) or []:
            nid = str(node.get("id", ""))
            x = node.get("x")
            y = node.get("y")
            if nid and x is not None and y is not None:
                positions[nid] = (float(x), float(y))
        return positions

    def _compute_bfs_positions(self) -> dict[str, tuple[float, float]]:
        """Assign deterministic (x, y) positions via BFS using actual lane lengths.

        The graph may contain disconnected components (e.g. charger spurs). Each
        component is laid out independently along the x-axis so lanes do not
        overlap. Within a component, each child node is placed ``lane.length``
        metres away from its parent in a deterministic angular fan.

        Performance: O(V + E) — linear in graph size.  For very large maps,
        provide explicit (x, y) coordinates in the YAML ``nodes`` block to
        skip this computation entirely.
        """
        positions: dict[str, tuple[float, float]] = {}
        lanes = self._fmap.all_lanes()
        if not lanes:
            return positions

        # Adjacency: node -> outgoing lanes (sorted for stability)
        successors: dict[str, list[Lane]] = {}
        all_nodes: set[str] = set()
        for lane in lanes:
            successors.setdefault(lane.from_node, []).append(lane)
            all_nodes.add(lane.from_node)
            all_nodes.add(lane.to_node)
        for node_list in successors.values():
            node_list.sort(key=lambda lane: lane.lane_id)

        # Build undirected connectivity for component detection.
        adj: dict[str, set[str]] = {node: set() for node in all_nodes}
        for lane in lanes:
            adj[lane.from_node].add(lane.to_node)
            adj[lane.to_node].add(lane.from_node)

        visited_nodes: set[str] = set()
        component_roots = sorted(all_nodes)
        component_index = 0
        component_spacing = self.COMPONENT_SPACING

        for start in component_roots:
            if start in visited_nodes:
                continue
            # Gather this connected component.
            component: list[str] = []
            stack = [start]
            while stack:
                node = stack.pop()
                if node in visited_nodes:
                    continue
                visited_nodes.add(node)
                component.append(node)
                stack.extend(sorted(adj[node]))

            # Pick a stable root for the component.
            root = min(component)
            base_x = component_index * component_spacing
            positions[root] = (base_x, 0.0)
            angles: dict[str, float] = {root: 0.0}
            frontier: deque[str] = deque([root])
            component_visited: set[str] = {root}

            while frontier:
                node = frontier.popleft()
                x, y = positions[node]
                parent_angle = angles[node]
                children = successors.get(node, [])
                if not children:
                    continue
                span = math.pi / 3.0
                start_angle = parent_angle if len(children) == 1 else parent_angle - span / 2.0
                step = span / (len(children) - 1) if len(children) > 1 else 0.0
                for idx, lane in enumerate(children):
                    child = lane.to_node
                    if child in component_visited:
                        continue
                    angle = start_angle + step * idx
                    length = max(lane.length, 0.0)
                    positions[child] = (
                        x + length * math.cos(angle),
                        y + length * math.sin(angle),
                    )
                    angles[child] = angle
                    component_visited.add(child)
                    frontier.append(child)

            component_index += 1

        # Any isolated nodes (no lanes) get a fallback row.
        fallback_idx = 0
        for node in sorted(all_nodes):
            if node not in positions:
                positions[node] = (fallback_idx * 10.0, 0.0)
                fallback_idx += 1
        return positions

    @property
    def fmap(self) -> FixedLaneMap:
        """Return the underlying `FixedLaneMap` (read-only access)."""
        return self._fmap

    def lane(self, lane_id: str) -> Lane | None:
        """Return the physical lane definition, or None if unknown."""
        return self._fmap.lane(lane_id)

    def length(self, lane_id: str) -> float:
        """Return lane length in metres; 0.0 for unknown lanes."""
        lane = self._fmap.lane(lane_id)
        return lane.length if lane is not None else 0.0

    def successors(self, node_id: str) -> list[str]:
        """Return lane ids leaving ``node_id``."""
        return self._fmap.lanes_out_of(node_id)

    def node_position(self, node_id: str) -> tuple[float, float]:
        """Return the (x, y) position of a node, defaulting to (0, 0)."""
        return self._positions.get(node_id, (0.0, 0.0))

    def charger_lanes(self) -> list[str]:
        """Return lane ids that are marked as charger bays."""
        return [lane.lane_id for lane in self._fmap.all_lanes() if lane.charger]

    def all_lanes(self) -> list[Lane]:
        """Return all physical lanes."""
        return self._fmap.all_lanes()

    def first_lane(self) -> str | None:
        """Return a stable first lane id for default robot placement."""
        lanes = self._fmap.all_lanes()
        return lanes[0].lane_id if lanes else None
