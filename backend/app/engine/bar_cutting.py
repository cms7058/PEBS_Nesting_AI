"""管材/棒材一维下料核算 —— 多根定尺 + 库存限制 + 余料优先(护城河路线三的一维版）。

FFD 启发式:零件长降序,逐根装入;先用余料原料,再用新定尺原料(受库存限制)。
含锯缝(每刀消耗 kerf)。产出切割出料表 + 各根余料长度,供登记复用。
规格(管材:外径+厚度;棒材:外径)用于截面积/重量核算与余料按规格匹配。
"""
from __future__ import annotations

import math

STEEL_DENSITY = 7.85e-6  # kg/mm^3,普通碳钢


def section_area(profile_type: str, od: float, thickness: float = 0.0) -> float:
    """截面积 mm²。管材:π/4(OD²−ID²);棒材:π/4·OD²。"""
    if profile_type == "tube":
        idd = max(od - 2 * thickness, 0.0)
        return math.pi / 4 * (od * od - idd * idd)
    return math.pi / 4 * od * od


def accounting(result: dict, profile_type: str, od: float,
               thickness: float = 0.0, density: float = STEEL_DENSITY) -> dict:
    """按规格做重量核算:净产品 / 投入新料 / 可回收余料 的重量(kg)。"""
    area = section_area(profile_type, od, thickness)
    prod_len = sum(l * c for b in result["bars"] for l, c in b["cuts"].items())
    new_input_len = sum(b["stock_length"] for b in result["bars"] if not b["is_remnant"])
    remnant_len = sum(b["remnant_length"] for b in result["bars"])
    return {
        "section_area_mm2": round(area, 1),
        "weight_kg_per_m": round(area * density * 1000, 3),
        "product_weight_kg": round(prod_len * area * density, 2),
        "input_weight_kg": round(new_input_len * area * density, 2),
        "remnant_weight_kg": round(remnant_len * area * density, 2),
    }


def nest_bars(pieces: list[tuple[float, int]], stock_length: float, stock_count: int,
              kerf: float = 0.0, remnant_bars: list[dict] | None = None) -> dict:
    """pieces:[(长度mm, 数量)];stock_length:新原料定尺;stock_count:可用新原料根数;
    remnant_bars:可优先使用的余料 [{id, length}]。"""
    remnant_bars = remnant_bars or []
    lengths = sorted((l for l, q in pieces for _ in range(q)), reverse=True)

    # 可用原料序列:余料(cost 0,优先)+ 新定尺(受库存限制)
    slots: list[dict] = [{"cap": r["length"], "rid": r["id"], "is_remnant": True} for r in remnant_bars]
    slots += [{"cap": stock_length, "rid": None, "is_remnant": False} for _ in range(stock_count)]

    bars: list[dict] = []          # 已开原料:{cap, used, cuts:{len:cnt}, is_remnant, rid}
    next_slot = 0
    shortfall = 0

    def place(length: float) -> bool:
        nonlocal next_slot
        need = length + kerf
        # 1) 已开原料 first-fit
        for b in bars:
            if b["used"] + need <= b["cap"] + 1e-6:
                b["used"] += need
                b["cuts"][length] = b["cuts"].get(length, 0) + 1
                return True
        # 2) 开新原料(按 slots 顺序:余料优先)
        while next_slot < len(slots):
            s = slots[next_slot]
            next_slot += 1
            if need <= s["cap"] + 1e-6:
                bars.append({"cap": s["cap"], "used": need, "cuts": {length: 1},
                             "is_remnant": s["is_remnant"], "rid": s["rid"]})
                return True
        return False

    for length in lengths:
        if not place(length):
            shortfall += 1

    # 出料表
    bars_out, new_idx, new_used, rem_used = [], 0, 0, 0
    total_piece = total_cap = 0.0
    for b in bars:
        if b["is_remnant"]:
            code = f"余料-{b['rid']}"
            rem_used += 1
        else:
            new_idx += 1
            new_used += 1
            code = f"BAR-{new_idx:03d}"
        piece_len = sum(l * c for l, c in b["cuts"].items())
        total_piece += piece_len
        total_cap += b["cap"]
        bars_out.append({
            "bar_code": code, "is_remnant": b["is_remnant"],
            "stock_length": round(b["cap"], 1),
            "used_length": round(b["used"], 1),
            "remnant_length": round(b["cap"] - b["used"], 1),
            "utilization": round(piece_len / b["cap"], 4) if b["cap"] else 0.0,
            "cuts": {round(l, 1): c for l, c in sorted(b["cuts"].items(), reverse=True)},
        })

    # 各零件已切/缺口
    demand_map: dict[float, int] = {}
    for l, q in pieces:
        demand_map[l] = demand_map.get(l, 0) + q
    placed_map: dict[float, int] = {}
    for b in bars:
        for l, c in b["cuts"].items():
            placed_map[l] = placed_map.get(l, 0) + c
    per_piece = [{"length": round(l, 1), "demand": q, "placed": placed_map.get(l, 0),
                  "shortfall": q - placed_map.get(l, 0)} for l, q in sorted(demand_map.items(), reverse=True)]

    return {
        "overall_utilization": round(total_piece / total_cap, 4) if total_cap else 0.0,
        "bars_used": new_used,
        "remnants_used": rem_used,
        "stock_available": stock_count,
        "total_shortfall": shortfall,
        "per_piece": per_piece,
        "bars": bars_out,
        "kerf": kerf,
    }
