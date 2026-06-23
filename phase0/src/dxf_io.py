"""DXF 读写与轮廓提取（第零阶段验证用）。

仅做最小可用解析：把 DXF 中的 LWPOLYLINE / POLYLINE 闭合轮廓提取为 Shapely 多边形。
真实工厂图纸的轮廓重组/清理（非闭合修复、圆弧拟合、重叠清理）属第一阶段几何层独立模块，
此处先用合成样本保证轮廓本身闭合干净。
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from shapely.geometry import Polygon


def load_parts(dxf_path: str | Path) -> list[Polygon]:
    """从 DXF 读取所有闭合多段线，返回零件多边形列表。"""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    parts: list[Polygon] = []
    for e in msp.query("LWPOLYLINE"):
        pts = [(p[0], p[1]) for p in e.get_points("xy")]
        if e.closed and len(pts) >= 3:
            poly = Polygon(pts)
            if poly.is_valid and poly.area > 1e-6:
                parts.append(poly)
    return parts


def save_parts(parts: list[Polygon], dxf_path: str | Path) -> None:
    """把零件多边形写入 DXF（每个零件一条闭合 LWPOLYLINE）。"""
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    for poly in parts:
        coords = list(poly.exterior.coords)[:-1]
        msp.add_lwpolyline(coords, close=True)
    doc.saveas(str(dxf_path))
