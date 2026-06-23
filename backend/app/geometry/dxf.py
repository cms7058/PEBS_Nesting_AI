"""DXF 解析 —— 提取闭合轮廓为零件。

最小可用版:读 LWPOLYLINE 闭合多段线。真实脏数据的轮廓重组/清理(非闭合修复、
圆弧拟合、重叠清理)为几何层独立预处理模块,后续单独投入(见设计文档 3.1)。
"""
from __future__ import annotations

import ezdxf
from shapely.geometry import Polygon

from app.schemas import Part


def parse_dxf(path: str) -> list[Part]:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    parts: list[Part] = []
    idx = 0
    for e in msp.query("LWPOLYLINE"):
        pts = [(p[0], p[1]) for p in e.get_points("xy")]
        if e.closed and len(pts) >= 3:
            poly = Polygon(pts)
            if poly.is_valid and poly.area > 1e-6:
                parts.append(Part(
                    id=f"part_{idx}",
                    polygon=[(x, y) for x, y in poly.exterior.coords],
                ))
                idx += 1
    return parts
