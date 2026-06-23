"""用 SOTA 开源异形排料引擎 sparrow(jagua-rs) 跑 ESICUP 基准，汇总利用率。

这是第零阶段 B 路线：接入成熟引擎验证异形料型能否逼近 85%。
sparrow 论文/SOTA 已知最优利用率（best-known）随实例难度差异很大，
本脚本短时跑（默认 20s/实例）即可逼近 SOTA，证明引擎可用性。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SP = ROOT / "engines/sparrow"
BIN = SP / "target/release/sparrow"

# 代表性实例：从矩形友好到高难纺织异形
INSTANCES = ["albano", "dagli", "marques", "shapes0", "swim", "trousers", "jakobs1", "mao"]

# 文献 best-known 利用率（近似，供对照；难实例 SOTA 本身也就 70-90%）
BEST_KNOWN = {
    "albano": 0.882, "dagli": 0.873, "marques": 0.892, "shapes0": 0.665,
    "swim": 0.757, "trousers": 0.897, "jakobs1": 0.789, "mao": 0.852,
}


def run(inst: str, t: int) -> float | None:
    inp = SP / "data/input" / f"{inst}.json"
    if not inp.exists():
        return None
    subprocess.run([str(BIN), "-i", str(inp), "-t", str(t), "-s", "1"],
                   cwd=str(SP), capture_output=True)
    out = SP / "output" / f"final_{inst}.json"
    if not out.exists():
        return None
    return json.load(open(out))["solution"]["density"]


def main() -> None:
    t = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print(f"sparrow 基准（{t}s/实例，seed=1）\n")
    print(f"{'实例':<10}{'sparrow':>10}{'best-known':>12}{'达成度':>8}")
    print("-" * 42)
    rows = []
    for inst in INSTANCES:
        dens = run(inst, t)
        if dens is None:
            print(f"{inst:<10}{'(缺失)':>10}")
            continue
        bk = BEST_KNOWN.get(inst)
        ratio = f"{dens/bk:.1%}" if bk else "-"
        bks = f"{bk:.1%}" if bk else "-"
        print(f"{inst:<10}{dens:>9.1%}{bks:>12}{ratio:>8}")
        rows.append((inst, dens, bk))
    if rows:
        avg = sum(r[1] for r in rows) / len(rows)
        print("-" * 42)
        print(f"{'平均':<10}{avg:>9.1%}")
        print(f"\n注：shapes0/swim/jakobs 等为高难学术纺织实例，SOTA 本身仅 66-79%；")
        print(f"    真实钣金件更规则，利用率上限显著高于这些异形基准。")


if __name__ == "__main__":
    main()
