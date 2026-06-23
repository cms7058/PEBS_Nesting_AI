"""工具集(Tools）—— Function Calling 封装求解器。

中性 JSON Schema 定义,按 provider 转 Anthropic / OpenAI 两种格式。
架构红线:LLM 只编排与解释,真正计算在这些工具里(sparrow / FFD)。

会话态:nest_2d 作用于「已从上传 DXF 载入的零件」(session.parts),
cut_1d 可由自然语言完全驱动(对应设计文档对话示例)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.engine.cut1d import cut_1d
from app.engine.sparrow_engine import nest_2d
from app.schemas import Part, Sheet


@dataclass
class Session:
    """一次对话的上下文:载入的零件、最近一次排料结果。"""
    parts: list[Part] = field(default_factory=list)
    last_nest: Any = None
    last_sheets: Any = None  # 最近一次固定板装箱出料表(2D)
    last_bars: Any = None    # 最近一次管/棒一维下料出料表(1D)


# ---- 工具实现(返回给 LLM 的结构化结果，需 JSON 可序列化）----

def _tool_cut_1d(session: Session, lengths_mm: list[float], quantities: list[int],
                 stock_length_mm: float, kerf_mm: float = 0.0) -> dict:
    pieces = list(zip(lengths_mm, quantities))
    r = cut_1d(pieces, stock_length_mm, kerf_mm)
    return {"bar_count": r.bar_count, "utilization": round(r.utilization, 4),
            "stock_length_mm": r.stock_length, "kerf_mm": r.kerf,
            "bars": r.bars, "remnant_mm": r.remnant}


def _tool_nest_2d(session: Session, sheet_width_mm: float, time_sec: int = 20) -> dict:
    if not session.parts:
        return {"error": "尚未载入零件,请先上传 DXF 图纸"}
    r = nest_2d(session.parts, Sheet(width=sheet_width_mm), time_sec=time_sec)
    session.last_nest = r
    return {"utilization": round(r.utilization, 4), "placed": r.part_count,
            "used_length_mm": round(r.used_length, 1), "sheet_width_mm": r.sheet_width,
            "run_time_sec": round(r.run_time_sec, 1)}


def _tool_calc_cost(session: Session, utilization: float, area_or_length: float,
                    unit_price: float) -> dict:
    """利用率损失成本:浪费量 = 用料 ×(1-利用率)。"""
    waste = area_or_length * (1 - utilization)
    return {"waste_qty": round(waste, 3), "waste_cost": round(waste * unit_price, 2),
            "saved_vs_50pct": round((utilization - 0.5) * area_or_length * unit_price, 2)}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema(中性）
    fn: Callable[..., dict]


TOOLS: list[Tool] = [
    Tool(
        name="cut_1d",
        description="一维下料优化(棒材/管材):给定各零件长度、数量、原料定尺与锯缝,返回最省切割方案与利用率。",
        parameters={
            "type": "object",
            "properties": {
                "lengths_mm": {"type": "array", "items": {"type": "number"}, "description": "各零件长度(mm)"},
                "quantities": {"type": "array", "items": {"type": "integer"}, "description": "对应数量,与 lengths_mm 一一对应"},
                "stock_length_mm": {"type": "number", "description": "原料定尺长度(mm)"},
                "kerf_mm": {"type": "number", "description": "锯缝宽(mm),默认 0"},
            },
            "required": ["lengths_mm", "quantities", "stock_length_mm"],
        },
        fn=_tool_cut_1d,
    ),
    Tool(
        name="nest_2d",
        description="二维排料(板材):对已从上传 DXF 载入的零件,按给定板宽自动排样,返回利用率与排料结果。需先上传图纸。",
        parameters={
            "type": "object",
            "properties": {
                "sheet_width_mm": {"type": "number", "description": "母板板宽(mm)"},
                "time_sec": {"type": "integer", "description": "求解时限秒,默认 20"},
            },
            "required": ["sheet_width_mm"],
        },
        fn=_tool_nest_2d,
    ),
    Tool(
        name="calc_cost",
        description="计算利用率对应的材料浪费量与成本(给定单价),用于向用户解释经营价值。",
        parameters={
            "type": "object",
            "properties": {
                "utilization": {"type": "number", "description": "利用率 0~1"},
                "area_or_length": {"type": "number", "description": "总用料(板材用面积/型材用长度)"},
                "unit_price": {"type": "number", "description": "单价(每面积/每长度)"},
            },
            "required": ["utilization", "area_or_length", "unit_price"],
        },
        fn=_tool_calc_cost,
    ),
]

BY_NAME = {t.name: t for t in TOOLS}


def dispatch(name: str, args: dict, session: Session) -> dict:
    tool = BY_NAME.get(name)
    if tool is None:
        return {"error": f"未知工具 {name}"}
    try:
        return tool.fn(session, **args)
    except Exception as e:  # 把异常作为工具结果回灌,让 LLM 解释/重试
        return {"error": str(e)}


def anthropic_schema() -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in TOOLS]


def openai_schema() -> list[dict]:
    return [{"type": "function",
             "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in TOOLS]
