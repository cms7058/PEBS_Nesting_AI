"""基于 NFP 的 Bottom-Left-Fill 放置 + GA 搜索（顺序/角度）。

place_nfp(): 给定零件序列与各自候选角度，做 NFP-BLF 紧贴放置，返回 NestResult。
optimize_ga(): 遗传算法搜索 (放置顺序, 每件角度)，最大化利用率。
"""
from __future__ import annotations

import random

from shapely.affinity import rotate, translate
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon

from nest_baseline import NestResult, Placement
from nfp import feasible_region

BIG_H = 100000.0  # 虚拟无限板高，最终用 used_height 计利用率


def _candidate_points(region) -> list[tuple[float, float]]:
    """从可行域几何提取候选参考点（边界顶点）。"""
    geoms = []
    if isinstance(region, (MultiPolygon, GeometryCollection)):
        geoms = list(region.geoms)
    else:
        geoms = [region]
    pts = []
    for g in geoms:
        if isinstance(g, Polygon) and not g.is_empty:
            pts.extend(list(g.exterior.coords))
            for ring in g.interiors:
                pts.extend(list(ring.coords))
    return pts


def _normalize(poly: Polygon) -> Polygon:
    minx, miny, _, _ = poly.bounds
    return translate(poly, -minx, -miny)


def place_nfp(
    parts: list[Polygon],
    order: list[int],
    angles: list[float],
    sheet_width: float,
    spacing: float = 2.0,
) -> NestResult:
    placed: list[Polygon] = []
    placements: list[Placement] = []
    part_area = 0.0
    used_height = 0.0

    for i in order:
        base = _normalize(rotate(parts[i], angles[i], origin="centroid"))
        # spacing：对部件外扩半个间距，等效零件间留缝
        moving = base.buffer(spacing * 0.5, join_style=2) if spacing else base
        moving = _normalize(moving)

        region = feasible_region(moving, placed, sheet_width, BIG_H)
        if region is None or region.is_empty:
            continue
        cands = _candidate_points(region)
        if not cands:
            continue
        # Bottom-Left：参考点 y 最小、再 x 最小
        px, py = min(cands, key=lambda p: (round(p[1], 3), round(p[0], 3)))

        final = translate(base, px, py)
        placed.append(translate(moving, px, py))
        placements.append(Placement(poly=final, angle=angles[i], index=i))
        part_area += parts[i].area
        used_height = max(used_height, final.bounds[3])

    return NestResult(placements, sheet_width, used_height, part_area)


# ---------------- GA ----------------

def _fitness(parts, order, angles, sheet_width) -> tuple[float, NestResult]:
    res = place_nfp(parts, order, angles, sheet_width)
    placed_all = len(res.placements) == len(parts)
    # 未全放下重罚，优先保证全部放入
    util = res.utilization * (1.0 if placed_all else 0.5)
    return util, res


def optimize_ga(
    parts: list[Polygon],
    sheet_width: float,
    angle_set: tuple[float, ...] = (0, 90, 180, 270),
    pop: int = 12,
    gens: int = 8,
    seed: int = 0,
):
    rng = random.Random(seed)
    n = len(parts)
    area_desc = sorted(range(n), key=lambda i: parts[i].area, reverse=True)

    def rand_indiv():
        order = area_desc[:] if rng.random() < 0.5 else rng.sample(range(n), n)
        angles = [rng.choice(angle_set) for _ in range(n)]
        return order, angles

    population = [rand_indiv() for _ in range(pop)]
    # 注入一个「面积降序 + 全 0 角」精英个体（强基线）
    population[0] = (area_desc[:], [0.0] * n)

    best_fit, best_res = -1.0, None
    for _ in range(gens):
        scored = []
        for order, angles in population:
            fit, res = _fitness(parts, order, angles, sheet_width)
            scored.append((fit, order, angles, res))
            if fit > best_fit:
                best_fit, best_res = fit, res
        scored.sort(key=lambda s: s[0], reverse=True)
        elites = scored[: max(2, pop // 3)]

        new_pop = [(e[1], e[2]) for e in elites]
        while len(new_pop) < pop:
            (_, o1, a1, _), (_, o2, a2, _) = rng.sample(elites, 2)
            # 顺序交叉 OX
            child_o = _ox(o1, o2, rng)
            child_a = [a1[i] if rng.random() < 0.5 else a2[i] for i in range(n)]
            # 变异
            if rng.random() < 0.3:
                p, q = rng.randrange(n), rng.randrange(n)
                child_o[p], child_o[q] = child_o[q], child_o[p]
            if rng.random() < 0.5:
                child_a[rng.randrange(n)] = rng.choice(angle_set)
            new_pop.append((child_o, child_a))
        population = new_pop

    return best_fit, best_res


def _ox(p1, p2, rng):
    n = len(p1)
    a, b = sorted(rng.sample(range(n), 2))
    child = [None] * n
    child[a:b] = p1[a:b]
    fill = [g for g in p2 if g not in child[a:b]]
    k = 0
    for i in range(n):
        if child[i] is None:
            child[i] = fill[k]
            k += 1
    return child
