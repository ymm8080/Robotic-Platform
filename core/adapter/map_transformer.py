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

For brands with a known affine offset (translation + rotation), use
``MapTransformer.from_affine()`` or ``MapTransformer.from_points()`` instead
of hand-rolling lambdas.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from core.messages import Pose


@dataclass
class MapTransformer:
    """Coordinate + lane mapping for one robot brand."""

    brand: str
    native_to_unified_pose: Callable[[float, float, float], Pose]
    unified_to_native_goal: Callable[[str], dict]
    native_to_unified_lane: Callable[[str], str | None]

    @classmethod
    def identity(cls, brand: str) -> MapTransformer:
        """No-op transformer for fleets already operating in the unified frame."""
        return cls(
            brand=brand,
            native_to_unified_pose=lambda x, y, theta: Pose(x=x, y=y, theta=theta),
            unified_to_native_goal=lambda lane_id: {"lane_id": lane_id},
            native_to_unified_lane=lambda lane_id: lane_id,
        )

    @classmethod
    def from_affine(
        cls,
        brand: str,
        a: float = 1.0,
        b: float = 0.0,
        c: float = 0.0,
        d: float = 1.0,
        tx: float = 0.0,
        ty: float = 0.0,
    ) -> MapTransformer:
        """Create a transformer from a 6-parameter affine transform.

        The native-to-unified mapping is::

            x' = a*x + b*y + tx
            y' = c*x + d*y + ty
            theta' = theta + atan2(c, a)

        For a pure rigid transform (translation + rotation by angle ``phi``)::

            a = cos(phi),  b = -sin(phi)
            c = sin(phi),  d = cos(phi)

        Parameters
        ----------
        brand
            Brand identifier for this transformer.
        a, b, c, d
            2x2 linear matrix entries (row-major: [[a, b], [c, d]]).
        tx, ty
            Translation offsets in unified-frame units (typically metres).
        """
        phi = math.atan2(c, a)

        def _pose(x: float, y: float, theta: float) -> Pose:
            return Pose(
                x=a * x + b * y + tx,
                y=c * x + d * y + ty,
                theta=theta + phi,
            )

        return cls(
            brand=brand,
            native_to_unified_pose=_pose,
            unified_to_native_goal=lambda lane_id: {"lane_id": lane_id},
            native_to_unified_lane=lambda lane_id: lane_id,
        )

    @classmethod
    def from_points(
        cls,
        brand: str,
        native_points: list[tuple[float, float]],
        unified_points: list[tuple[float, float]],
    ) -> MapTransformer:
        """Fit an affine transformer from corresponding point pairs.

        Uses least-squares to solve for the 6-parameter affine transform
        that best maps ``native_points`` → ``unified_points``.  A minimum
        of 3 non-collinear point pairs is required.

        Parameters
        ----------
        brand
            Brand identifier for this transformer.
        native_points
            Source coordinates in the vendor-native frame, e.g.
            ``[(x1, y1), (x2, y2), (x3, y3)]``.
        unified_points
            Target coordinates in the unified platform frame, in the same
            order as ``native_points``.

        Raises
        ------
        ValueError
            If fewer than 3 point pairs are provided, or if the points are
            collinear (degenerate system).
        """
        if len(native_points) < 3 or len(unified_points) < 3:
            raise ValueError(
                f"from_points requires at least 3 point pairs, "
                f"got {min(len(native_points), len(unified_points))}"
            )
        if len(native_points) != len(unified_points):
            raise ValueError(
                f"native_points ({len(native_points)}) and "
                f"unified_points ({len(unified_points)}) must have equal length"
            )

        n = len(native_points)

        # Build normal equations: A^T A * params = A^T b
        # Each point pair contributes 2 equations:
        #   a*x + b*y + tx = x'
        #   c*x + d*y + ty = y'
        # We solve for (a, b, tx) and (c, d, ty) separately — same
        # coefficient matrix, different RHS.
        #
        # Coefficient matrix M (2n x 3):
        #   row 2i:   [x_i, y_i, 1]
        #   row 2i+1: [x_i, y_i, 1]
        # RHS for x': [x'_1, y'_1, x'_2, y'_2, ...]
        #   We solve two systems: M3 @ [a, b, tx] = x'_values
        #                         M3 @ [c, d, ty] = y'_values
        # where M3 is (n x 3): [x_i, y_i, 1]

        # Compute M^T M (3x3) and M^T * rhs (3x1) for each of x', y'
        # M^T M is the same for both systems.
        mtm = [[0.0, 0.0, 0.0] for _ in range(3)]
        mtx_x = [0.0, 0.0, 0.0]  # M^T * x'_values
        mtx_y = [0.0, 0.0, 0.0]  # M^T * y'_values

        for i in range(n):
            xi, yi = native_points[i]
            xu, yu = unified_points[i]
            row = [xi, yi, 1.0]
            for r in range(3):
                for c in range(3):
                    mtm[r][c] += row[r] * row[c]
                mtx_x[r] += row[r] * xu
                mtx_y[r] += row[r] * yu

        # Solve 3x3 system via Cramer's rule
        a, b, tx = _solve_3x3(mtm, mtx_x)
        c, d, ty = _solve_3x3(mtm, mtx_y)

        return cls.from_affine(brand, a=a, b=b, c=c, d=d, tx=tx, ty=ty)

    def transform_pose(self, x: float, y: float, theta: float) -> Pose:
        return self.native_to_unified_pose(x, y, theta)

    def transform_goal(self, lane_id: str) -> dict:
        return self.unified_to_native_goal(lane_id)

    def transform_lane(self, native_lane: str) -> str | None:
        return self.native_to_unified_lane(native_lane)


def _solve_3x3(mat: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a 3x3 linear system using Cramer's rule.

    ``mat`` is row-major ``[[m00, m01, m02], [m10, m11, m12], [m20, m21, m22]]``.
    Returns ``[x0, x1, x2]`` such that ``mat @ x = rhs``.
    Raises ``ValueError`` if the matrix is singular (zero determinant).
    """
    m00, m01, m02 = mat[0]
    m10, m11, m12 = mat[1]
    m20, m21, m22 = mat[2]

    det = (m00 * (m11 * m22 - m12 * m21)
           - m01 * (m10 * m22 - m12 * m20)
           + m02 * (m10 * m21 - m11 * m20))

    if abs(det) < 1e-12:
        raise ValueError(
            "Singular matrix in from_points — points are likely collinear"
        )

    inv_det = 1.0 / det
    b0, b1, b2 = rhs

    x0 = ((b0 * (m11 * m22 - m12 * m21)
           - m01 * (b1 * m22 - m12 * b2)
           + m02 * (b1 * m21 - m11 * b2)) * inv_det)

    x1 = ((m00 * (b1 * m22 - m12 * b2)
           - b0 * (m10 * m22 - m12 * m20)
           + m02 * (m10 * b2 - b1 * m20)) * inv_det)

    x2 = ((m00 * (m11 * b2 - b1 * m21)
           - m01 * (m10 * b2 - b1 * m20)
           + b0 * (m10 * m21 - m11 * m20)) * inv_det)

    return [x0, x1, x2]