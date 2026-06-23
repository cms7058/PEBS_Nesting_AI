"""NFP 临界多边形（No-Fit Polygon）—— 异形排料核心壁垒。

用 pyclipper 的 Minkowski 和计算 NFP：B 绕 A 滑动而不重叠时，B 参考点的轨迹。
    NFP_{A,B} = A ⊕ (-B)        （Minkowski sum，B 关于其参考点取反）
B 参考点取部件自身坐标原点 (0,0)，部件坐标已平移到第一象限。

放置判定（Bottom-Left-Fill）：
    可行域 = IFP(板, B) − ∪ NFP(已放件_i, B)
    候选点 = 可行域边界顶点；取 y 最小、再 x 最小者 = 最贴底左的落点。
"""
from __future__ import annotations

import pyclipper
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

SCALE = 1000  # 整数化缩放（pyclipper 用整型坐标）


def _to_int(coords) -> list[tuple[int, int]]:
    return [(int(round(x * SCALE)), int(round(y * SCALE))) for x, y in coords]


def _to_float(path) -> list[tuple[float, float]]:
    return [(x / SCALE, y / SCALE) for x, y in path]


def _ring(poly: Polygon) -> list[tuple[float, float]]:
    return list(poly.exterior.coords)[:-1]


def nfp(fixed: Polygon, moving: Polygon) -> Polygon | MultiPolygon | None:
    """计算 moving 绕 fixed 的 NFP（参考点轨迹围成的禁止区域）。"""
    a = _to_int(_ring(fixed))
    b_ref = [(-x, -y) for x, y in _ring(moving)]
    b = _to_int(b_ref)
    try:
        solution = pyclipper.MinkowskiSum(a, b, True)
    except Exception:
        return None
    polys = []
    for path in solution:
        if len(path) >= 3:
            p = Polygon(_to_float(path))
            if p.is_valid and p.area > 1e-9:
                polys.append(p)
    if not polys:
        return None
    # 取面积最大的外轮廓作为 NFP（保守：忽略凹腔内可滑入的孔）
    polys.sort(key=lambda p: p.area, reverse=True)
    return polys[0]


def ifp_rect(moving: Polygon, sheet_w: float, sheet_h: float) -> Polygon | None:
    """矩形板的内嵌可行域 IFP：moving 参考点可落位且整体不出板的矩形区域。"""
    bxmin, bymin, bxmax, bymax = moving.bounds
    x0, x1 = -bxmin, sheet_w - bxmax
    y0, y1 = -bymin, sheet_h - bymax
    if x1 < x0 or y1 < y0:
        return None
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def feasible_region(
    moving: Polygon, placed: list[Polygon], sheet_w: float, sheet_h: float
):
    """可行域 = IFP − ∪NFP。返回 shapely 几何或 None。"""
    ifp = ifp_rect(moving, sheet_w, sheet_h)
    if ifp is None or ifp.area <= 0:
        return None
    forbidden = []
    for f in placed:
        n = nfp(f, moving)
        if n is not None:
            forbidden.append(n)
    if not forbidden:
        return ifp
    region = ifp.difference(unary_union(forbidden))
    if region.is_empty:
        return None
    return region
