"""cut_1d —— 一维下料(棒材/管材),含锯缝。

First-Fit-Decreasing 启发式快速兜底(列生成法为后续优化项)。
每根原料定尺 stock_length;每刀消耗 kerf 锯缝。
"""
from __future__ import annotations

from app.schemas import Cut1DResult


def cut_1d(pieces: list[tuple[float, int]], stock_length: float, kerf: float = 0.0) -> Cut1DResult:
    """pieces: [(长度, 数量)]; 返回切割方案与利用率。"""
    # 展开并降序
    lengths: list[float] = []
    for length, qty in pieces:
        lengths.extend([length] * qty)
    lengths.sort(reverse=True)

    if any(l + kerf > stock_length for l in lengths):
        raise ValueError("存在零件长度超过原料定尺,无法下料")

    bars: list[list[float]] = []
    used: list[float] = []  # 各 bar 已用长度(含锯缝)
    for l in lengths:
        placed = False
        need = l + kerf
        for i in range(len(bars)):
            if used[i] + need <= stock_length + 1e-9:
                bars[i].append(l)
                used[i] += need
                placed = True
                break
        if not placed:
            bars.append([l])
            used.append(need)

    total_piece = sum(lengths)
    total_stock = len(bars) * stock_length
    remnant = [round(stock_length - u, 3) for u in used]
    return Cut1DResult(
        bars=bars,
        stock_length=stock_length,
        kerf=kerf,
        utilization=(total_piece / total_stock) if total_stock else 0.0,
        bar_count=len(bars),
        remnant=remnant,
    )
