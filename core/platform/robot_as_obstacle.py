"""Robot-as-Obstacle — 本体即障碍物 (v4.0 §5.3, 补丁1).

承认现实: 90% 商用底盘不开放局部障碍物, 只消费位姿.
- 每台机器人是一个动态长方体 (footprint) + 安全走廊, 不是圆形气泡.
- 安全距离硬约束 D_safe 由平台算, 不由机器人报 (v4.0 §6.1).
- 离群点剔除: 单机上报的障碍物必须被至少2台不同品牌交叉验证
  (实际剔除逻辑在 FixedLaneMap.report_observation; 这里只消费位姿).
- 承认盲区: 突然掉落的箱子交给机器人本地 Safety Laser.
- 不订阅原始点云/图像.

GitHub: multi_object_tracking_lidar (https://github.com/yzrobot/multi_object_tracking_lidar)
        — 外部感知可选增强 (CCTV/独立激光雷达站), 非强制.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from core.platform.fixed_lane_map import FixedLaneMap
from core.safety.safe_distance import SafeDistanceCalculator


@dataclass
class Footprint:
    """动态长方体 (v4.0 §5.3): 位置 + 朝向 + 半长半宽 + 安全走廊."""

    robot_id: str
    x: float
    y: float
    theta: float            # 朝向 (rad)
    half_length: float      # 车体半长
    half_width: float       # 车体半宽
    corridor: float = 0.0   # 安全走廊半径 (safe distance), 用于碰撞粗判

    def contains(self, x: float, y: float) -> bool:
        """点是否落入长方体 (含安全走廊). 先粗判走廊圆, 再精判旋转矩形."""
        if (self.x - x) ** 2 + (self.y - y) ** 2 > (self.half_length + self.corridor) ** 2:
            return False
        # 旋转到车体坐标系
        dx, dy = x - self.x, y - self.y
        c, s = math.cos(-self.theta), math.sin(-self.theta)
        lx = c * dx - s * dy
        ly = s * dx + c * dy
        return abs(lx) <= self.half_length + self.corridor and abs(ly) <= self.half_width + self.corridor


class RobotAsObstacle:
    """Maintains per-robot rectangular footprints and injects virtual walls."""

    MANUAL_WALL_RADIUS = 1.5  # SOP-YELLOW 步骤2a: 1.5m 半径虚拟墙

    def __init__(self, fmap: FixedLaneMap, safe_distance: SafeDistanceCalculator | None = None) -> None:
        self.fmap = fmap
        self.safe_distance = safe_distance or SafeDistanceCalculator()
        self._footprints: dict[str, Footprint] = {}

    def update(
        self,
        robot_id: str,
        x: float,
        y: float,
        theta: float,
        velocity: float,
        rtt: float = 0.1,
        half_length: float = 0.4,
        half_width: float = 0.3,
    ) -> Footprint:
        """Recompute a robot's footprint + safety corridor from live pose."""
        corridor = self.safe_distance.compute(velocity, rtt).applied
        fp = Footprint(
            robot_id=robot_id, x=x, y=y, theta=theta,
            half_length=half_length, half_width=half_width, corridor=corridor,
        )
        self._footprints[robot_id] = fp
        return fp

    def mark_manual(self, robot_id: str, x: float, y: float) -> None:
        """SOP-YELLOW: mark a degraded robot as a fixed 1.5 m virtual wall."""
        fp = Footprint(
            robot_id=robot_id, x=x, y=y, theta=0.0,
            half_length=0.0, half_width=0.0, corridor=self.MANUAL_WALL_RADIUS,
        )
        self._footprints[robot_id] = fp
        self.fmap.add_virtual_wall(x, y, self.MANUAL_WALL_RADIUS)

    def clear(self, robot_id: str) -> None:
        self._footprints.pop(robot_id, None)

    def footprints(self) -> list[Footprint]:
        return list(self._footprints.values())

    def collides(self, x: float, y: float, exclude: str | None = None) -> str | None:
        """Return the robot_id whose footprint contains (x,y), or None."""
        for fp in self._footprints.values():
            if exclude and fp.robot_id == exclude:
                continue
            if fp.contains(x, y):
                return fp.robot_id
        return None

    def overlapping_pairs(self) -> list[tuple[str, str]]:
        """Return unordered pairs of robot_ids whose rectangular footprints overlap.

        Uses the Separating Axis Theorem for oriented bounding boxes.
        """
        fps = list(self._footprints.values())
        pairs: list[tuple[str, str]] = []
        for i in range(len(fps)):
            for j in range(i + 1, len(fps)):
                if self._obb_overlap(fps[i], fps[j]):
                    pairs.append((fps[i].robot_id, fps[j].robot_id))
        return pairs

    @staticmethod
    def _obb_overlap(a: Footprint, b: Footprint) -> bool:
        """SAT for two oriented rectangles."""
        # rectangle corners in world coordinates
        def corners(fp: Footprint) -> list[tuple[float, float]]:
            c, s = math.cos(fp.theta), math.sin(fp.theta)
            lx, ly = fp.half_length + fp.corridor, fp.half_width + fp.corridor
            local = [(-lx, -ly), (lx, -ly), (lx, ly), (-lx, ly)]
            out: list[tuple[float, float]] = []
            for dx, dy in local:
                out.append((fp.x + c * dx - s * dy, fp.y + s * dx + c * dy))
            return out

        ac = corners(a)
        bc = corners(b)

        # axes to test: normals of each rectangle's edges
        axes: list[tuple[float, float]] = []
        for pts in (ac, bc):
            for k in range(4):
                x1, y1 = pts[k]
                x2, y2 = pts[(k + 1) % 4]
                edge = (x2 - x1, y2 - y1)
                # normal
                nx, ny = -edge[1], edge[0]
                norm = math.hypot(nx, ny)
                if norm > 1e-9:
                    axes.append((nx / norm, ny / norm))

        for ax, ay in axes:
            amin, amax = min(ax * x + ay * y for x, y in ac), max(ax * x + ay * y for x, y in ac)
            bmin, bmax = min(ax * x + ay * y for x, y in bc), max(ax * x + ay * y for x, y in bc)
            if amax < bmin or bmax < amin:
                return False
        return True
