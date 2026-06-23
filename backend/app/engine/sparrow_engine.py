"""nest_2d —— 二维排料引擎,封装 sparrow(jagua-rs)。

把零件多边形 + 母板转成 sparrow JSON,调用二进制求解,解析回放置与利用率。
sparrow 为 strip-packing:定宽(strip_height)= 板宽,最小化长度。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from shapely.geometry import Polygon

from app.config import settings
from app.schemas import NestResult, Part, Placement, Sheet


def _to_sparrow_input(parts: list[Part], sheet: Sheet) -> dict:
    items = []
    for i, p in enumerate(parts):
        poly = Polygon(p.polygon)
        if not poly.is_valid:
            poly = poly.buffer(0)
        minx, miny, _, _ = poly.bounds
        # 平移到第一象限,闭合
        ring = [(x - minx, y - miny) for x, y in poly.exterior.coords]
        items.append({
            "id": i,
            "demand": p.demand,
            "allowed_orientations": p.allowed_rotations,
            "shape": {"type": "simple_polygon", "data": [[x, y] for x, y in ring]},
        })
    return {"name": "nest_job", "items": items, "strip_height": sheet.width}


def nest_2d(parts: list[Part], sheet: Sheet, time_sec: int | None = None) -> NestResult:
    """对零件做二维排料,返回放置与利用率。"""
    if not Path(settings.sparrow_bin).exists():
        raise RuntimeError(
            f"sparrow 引擎未构建: {settings.sparrow_bin}（见 phase0/README，cargo build --release）"
        )

    inp = _to_sparrow_input(parts, sheet)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        in_path = td / "job.json"
        in_path.write_text(json.dumps(inp))
        sp_root = Path(settings.sparrow_bin).resolve().parents[2]  # engines/sparrow
        proc = subprocess.run(
            [settings.sparrow_bin, "-i", str(in_path),
             "-t", str(time_sec or settings.nest_time_sec), "-s", "1"],
            cwd=str(sp_root), capture_output=True, text=True,
        )
        out_path = sp_root / "output" / f"final_{inp['name']}.json"
        if not out_path.exists():
            raise RuntimeError(f"sparrow 未产出结果\n{proc.stderr[-800:]}")
        sol = json.loads(out_path.read_text())

    solution = sol["solution"]
    layout = solution["layout"]
    placements = []
    for pi in layout["placed_items"]:
        t = pi["transformation"]
        placements.append(Placement(
            part_id=parts[pi["item_id"]].id if pi["item_id"] < len(parts) else str(pi["item_id"]),
            rotation=t["rotation"],
            x=t["translation"][0],
            y=t["translation"][1],
        ))
    return NestResult(
        placements=placements,
        utilization=solution["density"],
        used_length=solution.get("strip_width", 0.0),
        sheet_width=sheet.width,
        part_count=len(placements),
        run_time_sec=solution.get("run_time_sec", 0.0),
    )
