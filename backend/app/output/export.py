"""排料图与切割码输出 —— SVG / DXF / NC。

export_layout：把排料结果渲染为 SVG(可视化)、DXF(回流 CAD)、NC(切割机)。
NC 为最小 G 代码骨架(G0 快移 + G1 沿轮廓切割),供演示;实际机型后处理另配。
"""
from __future__ import annotations

import math

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from app.schemas import NestResult, Part


def _placed_polygons(parts: list[Part], res: NestResult) -> list[tuple[str, Polygon]]:
    by_id = {p.id: p for p in parts}
    out = []
    for pl in res.placements:
        base = by_id.get(pl.part_id)
        if base is None:
            continue
        poly = Polygon(base.polygon)
        minx, miny, _, _ = poly.bounds
        poly = translate(poly, -minx, -miny)
        poly = rotate(poly, pl.rotation, origin=(0, 0), use_radians=False)
        poly = translate(poly, pl.x, pl.y)
        out.append((pl.part_id, poly))
    return out


def to_svg(parts: list[Part], res: NestResult) -> str:
    placed = _placed_polygons(parts, res)
    w, h = res.sheet_width, max(res.used_length, 1.0)
    palette = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
               "#edc948", "#b07aa1", "#ff9da7", "#9c755f"]
    body = [f'<rect x="0" y="0" width="{w:.1f}" height="{h:.1f}" '
            'fill="none" stroke="#333" stroke-width="2"/>']
    for i, (_, poly) in enumerate(placed):
        # 展示层交换轴(X=板宽，Y=长度)，与 /layout、Konva 一致
        pts = " ".join(f"{y:.2f},{x:.2f}" for x, y in poly.exterior.coords)
        body.append(f'<polygon points="{pts}" fill="{palette[i % len(palette)]}" '
                    'fill-opacity="0.7" stroke="#222" stroke-width="0.5"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -10 {w+20:.0f} {h+20:.0f}" '
            f'width="800">{"".join(body)}'
            f'<text x="0" y="-2" font-size="{max(h/40,6):.0f}" fill="#333">'
            f'利用率 {res.utilization:.1%}</text></svg>')


def to_nc(parts: list[Part], res: NestResult, feed: int = 1500) -> str:
    """最小 NC(G 代码)骨架:逐零件沿轮廓切割。"""
    placed = _placed_polygons(parts, res)
    lines = ["%", "G21 G90 (mm, absolute)", f"F{feed}"]
    for pid, poly in placed:
        coords = list(poly.exterior.coords)
        x0, y0 = coords[0]
        lines.append(f"(part {pid})")
        lines.append(f"G0 X{x0:.3f} Y{y0:.3f}")
        lines.append("M3 (pierce on)")
        for x, y in coords[1:]:
            lines.append(f"G1 X{x:.3f} Y{y:.3f}")
        lines.append("M5 (pierce off)")
    lines += ["M2", "%"]
    return "\n".join(lines)


def to_dxf_text(parts: list[Part], res: NestResult) -> str:
    """把排料后的零件写为 DXF(用 ezdxf 生成,返回字符串)。"""
    import io

    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for _, poly in _placed_polygons(parts, res):
        msp.add_lwpolyline(list(poly.exterior.coords)[:-1], close=True)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue()
