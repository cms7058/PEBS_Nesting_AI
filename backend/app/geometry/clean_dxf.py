"""DXF 脏数据预处理 —— 真实 CAD 展开图的入口质量保障(设计文档 §3.1 的「脏活」)。

真实展开图常见问题:散乱 LINE/ARC/SPLINE 不成闭合多段线、轮廓有微小缺口、
折弯线/标注/文字混在图里、零件含内孔。本模块:
1. 把所有曲线实体(LINE/ARC/CIRCLE/ELLIPSE/SPLINE/LWPOLYLINE/POLYLINE)统一展平为线段;
2. 剔除折弯线层 / 标注文字等非轮廓实体;
3. 用 shapely polygonize 重组闭合轮廓,set_precision 吸附小缺口;
4. 识别外轮廓与内孔(被包含的环=孔),每个零件=外轮廓(+孔)。
返回 (parts, diagnostics)。
"""
from __future__ import annotations

import ezdxf
from ezdxf import path as ezpath
from shapely import set_precision
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

from app.schemas import Part

# 折弯线 / 非轮廓层关键字(按层名粗匹配,大小写不敏感)
BEND_KEYWORDS = ("bend", "折弯", "v-cut", "vcut", "fold", "score")
SKIP_TYPES = {"DIMENSION", "TEXT", "MTEXT", "LEADER", "MLEADER", "HATCH", "ATTDEF", "ATTRIB", "POINT"}


def _is_bend_layer(layer: str) -> bool:
    low = (layer or "").lower()
    return any(k in low for k in BEND_KEYWORDS)


def clean_dxf(file_path: str, sag: float = 0.2, gap_tol: float = 0.5) -> tuple[list[Part], dict]:
    """sag:圆弧展平弦高(mm,越小越精细);gap_tol:缺口吸附容差(mm)。"""
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    diag = {
        "entities_total": 0, "by_type": {}, "bend_skipped": 0, "noncurve_skipped": 0,
        "lines_built": 0, "contours": 0, "parts": 0, "holes": 0, "gap_tol_mm": gap_tol,
    }
    lines: list[LineString] = []

    for e in msp:
        diag["entities_total"] += 1
        t = e.dxftype()
        diag["by_type"][t] = diag["by_type"].get(t, 0) + 1
        if t in SKIP_TYPES:
            diag["noncurve_skipped"] += 1
            continue
        if _is_bend_layer(getattr(e.dxf, "layer", "")):
            diag["bend_skipped"] += 1
            continue
        try:
            p = ezpath.make_path(e)
            pts = [(v.x, v.y) for v in p.flattening(sag)]
        except Exception:
            continue
        if len(pts) >= 2:
            lines.append(LineString(pts))
            diag["lines_built"] += 1

    if not lines:
        return [], diag

    # 节点化 + 吸附小缺口,再 polygonize 重组闭合轮廓(孔已并入多边形 interiors)
    merged = unary_union(lines)
    merged = set_precision(merged, gap_tol)  # 栅格吸附:闭合 < gap_tol 的缺口并节点化
    polys = [pp for pp in polygonize(merged) if pp.area > 1.0]
    diag["contours"] = len(polys)

    # 收集所有孔(内环)。落在别的轮廓孔里的面=孔内填充,丢弃。
    hole_polys = [Polygon(r) for p in polys for r in p.interiors]
    parts: list[Part] = []
    idx = 0
    for p in polys:
        if any(hp.contains(p.representative_point()) for hp in hole_polys):
            continue  # 孔内填充面,非真实零件
        holes = [[(x, y) for x, y in r.coords] for r in p.interiors]
        diag["holes"] += len(holes)
        parts.append(Part(
            id=f"part_{idx}",
            polygon=[(x, y) for x, y in p.exterior.coords],
            holes=holes or None,
        ))
        idx += 1

    diag["parts"] = len(parts)
    return parts, diag
