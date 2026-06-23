"""ESICUP 标准异形排样基准实例解析（XML → shapely 多边形）。

数据集：https://github.com/ESICUP/datasets  → 2d_irregular/{albano,shapes,swim,...}
每个实例：一块母板 board + 若干 piece（含数量 quantity 与允许旋转角 orientation）。
返回 (parts, allowed_angles, board_width, board_height)，parts 已按 quantity 展开。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

NS = "{http://www.fe.up.pt/~esicup/nesting.xsd}"


def _polygon_coords(poly_el) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for seg in poly_el.find(f"{NS}lines").findall(f"{NS}segment"):
        x0, y0 = float(seg.get("x0")), float(seg.get("y0"))
        if not pts or pts[-1] != (x0, y0):
            pts.append((x0, y0))
    return pts


def load_instance(xml_path: str | Path):
    """解析 ESICUP XML，返回 (parts, angles_per_part, board_w, board_h)。"""
    root = ET.parse(str(xml_path)).getroot()

    polygons_el = root.find(f"{NS}polygons")
    if polygons_el is None:
        raise ValueError("实例无 <polygons> 节点（格式不兼容，跳过）")
    polys: dict[str, Polygon] = {}
    for pel in polygons_el.findall(f"{NS}polygon"):
        coords = _polygon_coords(pel)
        if len(coords) >= 3:
            p = Polygon(coords)
            if not p.is_valid:
                p = p.buffer(0)
            polys[pel.get("id")] = p

    problem = root.find(f"{NS}problem")

    # 母板
    board_el = problem.find(f"{NS}boards").find(f"{NS}piece")
    board_poly = polys[board_el.find(f"{NS}component").get("idPolygon")]
    bxmin, bymin, bxmax, bymax = board_poly.bounds
    board_w, board_h = bxmax - bxmin, bymax - bymin

    parts: list[Polygon] = []
    angles_per_part: list[list[float]] = []
    for piece in problem.find(f"{NS}lot").findall(f"{NS}piece"):
        qty = int(piece.get("quantity", "1"))
        comp = piece.find(f"{NS}component")
        base = polys[comp.get("idPolygon")]
        minx, miny, _, _ = base.bounds
        base = translate(base, -minx, -miny)
        orient = piece.find(f"{NS}orientation")
        if orient is not None:
            angles = [float(e.get("angle")) for e in orient.findall(f"{NS}enumeration")]
        else:
            angles = [0.0, 90.0, 180.0, 270.0]
        for _ in range(qty):
            parts.append(base)
            angles_per_part.append(angles or [0.0])

    return parts, angles_per_part, board_w, board_h


def to_dxf(parts: list[Polygon], dxf_path: str | Path) -> None:
    from dxf_io import save_parts
    save_parts(parts, dxf_path)


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parents[1] / "datasets/esicup/2d_irregular"
    names = sys.argv[1:] or ["albano", "shapes", "swim", "dighe", "jakobs"]
    for name in names:
        xml = next((root / name).glob("*.xml"), None)
        if not xml:
            print(f"{name:10s}  (无 xml，跳过)")
            continue
        parts, angles, w, h = load_instance(xml)
        tot = sum(p.area for p in parts)
        print(f"{name:10s}  零件={len(parts):3d}  母板={w:.0f}x{h:.0f}  "
              f"件总面积={tot:.0f}  理论上界利用率={tot/(w*h):.1%}（单板内）")
