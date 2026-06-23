"""二维异形排料基线算法（第零阶段验证）。

策略：Bottom-Left 贪心放置 + 多角度候选 + Shapely 碰撞检测。
这是文档「能跑 → 够用 → 领先」三步中的 *基线*，用于跑出可对比的利用率数字。
后续进阶（NFP + GA/SA，基于 Deepnest 二开）在此基线之上替换 place() 即可。

利用率定义：sum(零件面积) / (板宽 × 实际用到的板高)。
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon
from shapely.strtree import STRtree


@dataclass
class Placement:
    poly: Polygon          # 已放置在板坐标系中的多边形
    angle: float
    index: int             # 原始零件序号


@dataclass
class NestResult:
    placements: list[Placement]
    sheet_width: float
    used_height: float
    part_area: float

    @property
    def utilization(self) -> float:
        used = self.sheet_width * self.used_height
        return self.part_area / used if used > 0 else 0.0


def place(
    parts: list[Polygon],
    sheet_width: float,
    angles: tuple[float, ...] = (0, 90, 180, 270),
    spacing: float = 2.0,
    step: float = 5.0,
) -> NestResult:
    """按面积降序，对每个零件做 Bottom-Left 候选扫描放置。"""
    order = sorted(range(len(parts)), key=lambda i: parts[i].area, reverse=True)

    placed: list[Polygon] = []
    placements: list[Placement] = []
    part_area = 0.0
    used_height = 0.0

    for i in order:
        base = parts[i]
        best = None  # (y, x, poly, angle)
        for ang in angles:
            rp = rotate(base, ang, origin="centroid")
            minx, miny, maxx, maxy = rp.bounds
            rp = translate(rp, -minx, -miny)
            w = maxx - minx
            if w > sheet_width:
                continue
            # 在板宽范围内自下而上、自左而右扫描第一个不碰撞的落点
            tree = STRtree(placed) if placed else None
            y = 0.0
            placed_here = None
            ymax_scan = used_height + (maxy - miny) + spacing
            while y <= ymax_scan and placed_here is None:
                x = 0.0
                while x + w <= sheet_width + 1e-6:
                    cand = translate(rp, x, y)
                    if _no_overlap(cand, tree, placed, spacing):
                        placed_here = (y, x, cand, ang)
                        break
                    x += step
                if placed_here:
                    break
                y += step
            if placed_here and (best is None or placed_here[0] < best[0]):
                best = placed_here

        if best is None:
            continue
        y, x, cand, ang = best
        placed.append(cand)
        placements.append(Placement(poly=cand, angle=ang, index=i))
        part_area += base.area
        used_height = max(used_height, cand.bounds[3])

    return NestResult(placements, sheet_width, used_height, part_area)


def _no_overlap(cand: Polygon, tree: STRtree, placed: list[Polygon], spacing: float) -> bool:
    if tree is None:
        return True
    cb = cand.buffer(spacing * 0.5)
    for idx in tree.query(cb):
        if cb.intersects(placed[idx]):
            return False
    return True
