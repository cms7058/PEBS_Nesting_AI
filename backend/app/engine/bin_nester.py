"""nest_sheets —— 固定尺寸板材的多张装箱(方案乙),封装 bin_nester(jagua-rs BPP)。

输入:零件(多边形 + 所需数量)、板材长宽、可用张数。
输出:出料表(每张板:板料编码、各零件号数量、利用率、几何)+ 汇总(用板数、总利用率、缺口)。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from shapely.geometry import Polygon

from app.config import settings
from app.schemas import Part


def nest_sheets(parts: list[Part], demands: dict[str, int],
                sheet_length: float, sheet_width: float, sheet_count: int,
                time_sec: int = 12, remnants: list[dict] | None = None) -> dict:
    """parts:可用零件;demands:{part_id: 数量};板材 长×宽;sheet_count:可用张数。
    remnants:可选,优先使用的余料矩形 [{id, w, h}],作为低 id/零成本 bin 先消耗。"""
    remnants = remnants or []
    if not Path(settings.bin_nester_bin).exists():
        raise RuntimeError(
            f"bin_nester 未构建: {settings.bin_nester_bin}(cargo build --release)"
        )

    # 组装 ExtBPInstance,item id 连续 0..n
    items, idmap = [], []
    for p in parts:
        qty = int(demands.get(p.id, p.demand))
        if qty <= 0:
            continue
        poly = Polygon(p.polygon)
        if not poly.is_valid:
            poly = poly.buffer(0)
        minx, miny, _, _ = poly.bounds
        ring = [[round(x - minx, 3), round(y - miny, 3)] for x, y in poly.exterior.coords]
        items.append({
            "id": len(idmap), "demand": qty,
            "allowed_orientations": p.allowed_rotations,
            "shape": {"type": "simple_polygon", "data": ring},
            "min_quality": None,
        })
        idmap.append((p.id, qty, poly.area))

    if not items:
        raise ValueError("没有数量>0 的零件")

    # bins:余料矩形(id 0..k-1,stock 1,cost 0,优先消耗)+ 整张板(id k)
    bins = []
    for r in remnants:
        bins.append({
            "id": len(bins),
            "shape": {"type": "rectangle",
                      "data": {"x_min": 0, "y_min": 0, "width": r["w"], "height": r["h"]}},
            "stock": 1, "cost": 0,
        })
    sheet_bin_id = len(bins)
    bins.append({
        "id": sheet_bin_id,
        "shape": {"type": "rectangle",
                  "data": {"x_min": 0, "y_min": 0,
                           "width": sheet_length, "height": sheet_width}},
        "stock": sheet_count, "cost": 1,
    })
    inst = {"name": "sheets", "items": items, "bins": bins}

    with tempfile.TemporaryDirectory() as td:
        ip, op = Path(td) / "in.json", Path(td) / "out.json"
        ip.write_text(json.dumps(inst))
        proc = subprocess.run(
            [settings.bin_nester_bin, "-i", str(ip), "-o", str(op), "-t", str(time_sec)],
            capture_output=True, text=True)
        if not op.exists():
            raise RuntimeError(f"bin_nester 失败\n{proc.stderr[-800:]}")
        sol = json.loads(op.read_text())

    # 出料表(区分余料板/新板)
    remnant_by_id = {i: r for i, r in enumerate(remnants)}  # bin_id → remnant
    sheets_out = []
    new_idx = 0
    new_sheets_used = 0
    for sh in sol["sheets"]:
        counts: dict[str, int] = {}
        for it in sh["items"]:
            pid = idmap[it["item_id"]][0]
            counts[pid] = counts.get(pid, 0) + 1
        bid = sh.get("bin_id", sheet_bin_id)
        if bid in remnant_by_id:
            code = f"余料-{remnant_by_id[bid]['id']}"
            is_remnant = True
        else:
            new_idx += 1
            new_sheets_used += 1
            code = f"SHEET-{new_idx:03d}"
            is_remnant = False
        sheets_out.append({
            "sheet_code": code,
            "is_remnant": is_remnant,
            "utilization": round(sh["density"], 4),
            "width": sh["width"], "height": sh["height"],
            "part_counts": counts,
            "items": [{"part_id": idmap[it["item_id"]][0], "points": it["points"]}
                      for it in sh["items"]],
        })

    # 各零件已排/缺口
    per_part = []
    for k, (pid, qty, _) in enumerate(idmap):
        placed = sol["placed_counts"][k]
        per_part.append({"part_id": pid, "demand": qty, "placed": placed,
                         "shortfall": qty - placed})

    remnants_used = sum(1 for s in sheets_out if s["is_remnant"])
    return {
        "overall_utilization": round(sol["density"], 4),
        "sheets_used": new_sheets_used,        # 仅整张新板数
        "remnants_used": remnants_used,        # 复用余料张数
        "sheets_available": sheet_count,
        "total_placed": sol["placed"],
        "total_shortfall": sol["shortfall"],
        "per_part": per_part,
        "sheets": sheets_out,
    }
