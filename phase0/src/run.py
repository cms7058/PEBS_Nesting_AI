"""第零阶段验证主入口：生成/读取样本 → 排料 → 出图 → 利用率报告。

用法：
    python src/run.py                 # 用合成样本跑全部
    python src/run.py path/to.dxf     # 跑指定 DXF
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

# macOS 中文字体，避免标题方块；缺失则静默回退
for _f in ("PingFang SC", "Heiti SC", "Arial Unicode MS"):
    matplotlib.rcParams["font.sans-serif"] = [_f]
    break
matplotlib.rcParams["axes.unicode_minus"] = False

from dxf_io import load_parts
from generate_samples import generate
from nest_baseline import NestResult, place
from nest_nfp import optimize_ga

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
SHEET_WIDTH = 1500.0  # mm，典型钣金板宽


def draw(res: NestResult, title: str, png_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, max(4, res.used_height / SHEET_WIDTH * 8)))
    ax.add_patch(
        mpatches.Rectangle((0, 0), res.sheet_width, res.used_height,
                           fill=False, edgecolor="black", lw=1.5)
    )
    for pl in res.placements:
        xs, ys = pl.poly.exterior.xy
        ax.fill(xs, ys, alpha=0.65, edgecolor="black", lw=0.6)
    ax.set_xlim(-20, res.sheet_width + 20)
    ax.set_ylim(-20, res.used_height + 20)
    ax.set_aspect("equal")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(png_path, dpi=110)
    plt.close(fig)


def run_one(name: str, parts: list, engine: str = "baseline") -> dict:
    t0 = time.time()
    if engine == "nfp":
        _, res = optimize_ga(parts, sheet_width=SHEET_WIDTH)
    else:
        res = place(parts, sheet_width=SHEET_WIDTH)
    dt = time.time() - t0
    OUT.mkdir(exist_ok=True)
    draw(res, f"{name} [{engine}] util={res.utilization:.1%}", OUT / f"{name}_{engine}.png")
    return {
        "name": name,
        "parts": len(parts),
        "placed": len(res.placements),
        "utilization": res.utilization,
        "used_height": res.used_height,
        "seconds": dt,
    }


def main() -> None:
    args = sys.argv[1:]
    engine = "baseline"
    if "--engine" in args:
        idx = args.index("--engine")
        engine = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    rows = []
    if args:
        for p in args:
            rows.append(run_one(Path(p).stem, load_parts(p), engine))
    else:
        for seed in (1, 2, 3):
            rows.append(run_one(f"sample_{seed}", generate(seed=seed, n_parts=30), engine))

    print("\n=== 第零阶段排料基线报告 ===")
    print(f"{'样本':<12}{'零件':>6}{'已放':>6}{'利用率':>10}{'耗时(s)':>10}")
    for r in rows:
        print(f"{r['name']:<12}{r['parts']:>6}{r['placed']:>6}"
              f"{r['utilization']:>9.1%}{r['seconds']:>10.2f}")
    avg = sum(r["utilization"] for r in rows) / len(rows)
    print(f"\n平均利用率: {avg:.1%}   目标线: ≥85%   "
          f"{'✅ 达标' if avg >= 0.85 else '⚠️ 未达标（基线预期，待 NFP+GA 进阶）'}")
    print(f"排料图已输出至 {OUT}/")


if __name__ == "__main__":
    main()
