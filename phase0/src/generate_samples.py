"""合成 DXF 样本生成器（第零阶段起步用，无需真实工厂图纸）。

生成三类零件混合的钣金样本：矩形、L 形、不规则凸/凹多边形，
覆盖异形套料的典型难度，用于跑利用率基线。
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from dxf_io import save_parts


def _rect(w: float, h: float) -> Polygon:
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


def _lshape(a: float, b: float, t: float) -> Polygon:
    return Polygon([(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)])


def _irregular(r: float, n: int, jitter: float, rng: random.Random) -> Polygon:
    pts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        rad = r * (1 - jitter + 2 * jitter * rng.random())
        pts.append((rad * math.cos(ang), rad * math.sin(ang)))
    return Polygon(pts)


def generate(
    seed: int = 42,
    n_parts: int = 30,
    rect_ratio: float = 0.5,
    irregular_ratio: float = 0.25,
) -> list[Polygon]:
    """生成混合样本。

    rect_ratio: 矩形件占比（真实钣金多为矩形为主，调高更贴近一阶段目标客户）。
    irregular_ratio: 高难随机凹异形占比（压力测试用）。
    """
    rng = random.Random(seed)
    parts: list[Polygon] = []
    for _ in range(n_parts):
        r = rng.random()
        if r < rect_ratio:
            kind = "rect"
        elif r < rect_ratio + irregular_ratio:
            kind = "irregular"
        else:
            kind = "l"
        if kind == "rect":
            p = _rect(rng.uniform(40, 160), rng.uniform(30, 120))
        elif kind == "l":
            a = rng.uniform(60, 140)
            b = rng.uniform(60, 140)
            p = _lshape(a, b, rng.uniform(20, 40))
        else:
            p = _irregular(rng.uniform(30, 70), rng.randint(5, 8), 0.35, rng)
        # 仅做 90° 倍数随机朝向（真实 DXF 为自然朝向，连续旋转由排料引擎决定）
        p = rotate(p, rng.choice([0, 90, 180, 270]), origin="centroid")
        minx, miny, _, _ = p.bounds
        parts.append(translate(p, -minx, -miny))
    return parts


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "samples"
    out.mkdir(exist_ok=True)
    for seed in (1, 2, 3):
        parts = generate(seed=seed, n_parts=30)
        path = out / f"sample_{seed}.dxf"
        save_parts(parts, path)
        print(f"wrote {path}  ({len(parts)} parts)")
