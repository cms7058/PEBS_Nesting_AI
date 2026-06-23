"""材料牌号 → 密度(kg/mm³),用于重量核算。

牌号决定:① 能否混用/余料能否复用(必须同牌号);② 密度→重量。
按牌号关键字粗匹配密度;未知默认碳钢。
"""
from __future__ import annotations

# 常见牌号建议(前端下拉用)
GRADES = {
    "plate": ["Q235", "Q355", "SPCC", "304不锈钢", "316不锈钢", "6061铝", "5052铝"],
    "tube": ["20#钢", "Q235", "304不锈钢", "316不锈钢", "6061铝"],
    "bar": ["45#钢", "Q235", "40Cr", "304不锈钢", "6061铝"],
}


def density_for(grade: str) -> float:
    """kg/mm³。铝≈2.70e-6,不锈钢≈7.93e-6,铜≈8.9e-6,碳钢默认 7.85e-6。"""
    g = (grade or "").lower()
    if any(k in g for k in ("铝", "al", "6061", "5052", "7075")):
        return 2.70e-6
    if any(k in g for k in ("不锈", "304", "316", "201", "ss")):
        return 7.93e-6
    if any(k in g for k in ("铜", "cu", "h62", "h59")):
        return 8.90e-6
    return 7.85e-6
