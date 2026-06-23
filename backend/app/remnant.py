"""余料资产管理 —— 登记/检索可复用余料(护城河路线三)。

- extract_remnant: 从一张已排板的零件占用,求剩余可用区域(自由面积 + 最大可用矩形)。
  最大空矩形用栅格化 + 直方图法(经典 largest-rectangle-in-binary-matrix)。
- 余料库持久化为 JSON 文件,使余料数据跨重启沉淀(数据飞轮)。
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

STORE = Path(__file__).resolve().parents[1] / "remnants.json"
GRID = 160  # 栅格分辨率(长边),越大越精确越慢


def _largest_free_rect(sheet_w: float, sheet_h: float,
                       part_polys: list[Polygon]) -> dict:
    """栅格化占用,求最大全空轴对齐矩形(返回 mm 尺寸与左下角)。"""
    occ = unary_union(part_polys) if part_polys else None
    # 栅格:长边 GRID 格
    nx = GRID if sheet_w >= sheet_h else max(8, int(GRID * sheet_w / sheet_h))
    ny = GRID if sheet_h > sheet_w else max(8, int(GRID * sheet_h / sheet_w))
    cw, ch = sheet_w / nx, sheet_h / ny

    # free[y][x] = 该格是否空闲
    free = [[True] * nx for _ in range(ny)]
    if occ is not None:
        from shapely.prepared import prep
        pocc = prep(occ)
        from shapely.geometry import Point
        for j in range(ny):
            cy = (j + 0.5) * ch
            for i in range(nx):
                if pocc.intersects(Point((i + 0.5) * cw, cy)):
                    free[j][i] = False

    # 直方图法求最大全空矩形
    heights = [0] * nx
    best = (0, 0, 0, 0)  # area_cells, w_cells, x0, y_top_row
    best_rect = {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
    for j in range(ny):
        for i in range(nx):
            heights[i] = heights[i] + 1 if free[j][i] else 0
        # 单调栈求该行直方图最大矩形
        stack: list[int] = []
        i = 0
        while i <= nx:
            cur = heights[i] if i < nx else 0
            if not stack or cur >= heights[stack[-1]]:
                stack.append(i)
                i += 1
            else:
                top = stack.pop()
                h = heights[top]
                left = stack[-1] + 1 if stack else 0
                w = i - left
                area = h * w
                if area > best[0]:
                    best = (area, w, left, j)
                    best_rect = {
                        "x": round(left * cw, 1),
                        "y": round((j + 1 - h) * ch, 1),
                        "w": round(w * cw, 1),
                        "h": round(h * ch, 1),
                    }
    return best_rect


def extract_remnant(sheet_w: float, sheet_h: float,
                    item_point_lists: list[list[list[float]]]) -> dict:
    """item_point_lists: 该板各零件绝对多边形点列。返回余料指标。"""
    parts = [Polygon(pts) for pts in item_point_lists if len(pts) >= 3]
    used = sum(p.area for p in parts)
    sheet_area = sheet_w * sheet_h
    rect = _largest_free_rect(sheet_w, sheet_h, parts)
    return {
        "sheet_w": sheet_w, "sheet_h": sheet_h,
        "free_area": round(sheet_area - used, 1),
        "free_ratio": round(1 - used / sheet_area, 4) if sheet_area else 0.0,
        "largest_rect": rect,
    }


# ---------------- 余料库(持久化）----------------

def _load() -> list[dict]:
    if STORE.exists():
        return json.loads(STORE.read_text())
    return []


def _save(items: list[dict]) -> None:
    STORE.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def list_remnants() -> list[dict]:
    return _load()


def register(sheet_code: str, material: str, info: dict) -> dict:
    rec = {
        "id": "R" + uuid.uuid4().hex[:8].upper(),
        "source": sheet_code,
        "material": material,
        "date": date.today().isoformat(),
        "status": "available",
        **info,
    }
    items = _load()
    items.append(rec)
    _save(items)
    return rec


def delete(remnant_id: str) -> bool:
    items = _load()
    new = [r for r in items if r["id"] != remnant_id]
    if len(new) == len(items):
        return False
    _save(new)
    return True


def consume(remnant_id: str) -> bool:
    """标记余料已被使用(复用排版后)。"""
    items = _load()
    hit = False
    for r in items:
        if r["id"] == remnant_id:
            r["status"] = "consumed"
            hit = True
    if hit:
        _save(items)
    return hit
