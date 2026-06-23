"""数据契约(Pydantic）—— 排料任务的输入/输出模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

Point = tuple[float, float]


class Part(BaseModel):
    """一个待排零件。"""
    id: str
    polygon: list[Point] = Field(..., description="闭合外轮廓点列(mm)")
    holes: list[list[Point]] | None = Field(None, description="内孔轮廓(净面积/重量用)")
    demand: int = Field(1, ge=1, description="需求数量")
    allowed_rotations: list[float] = Field(
        default_factory=lambda: [0.0, 90.0, 180.0, 270.0],
        description="允许旋转角(度)",
    )


class Sheet(BaseModel):
    """母板(板材)。二维排料按定宽 strip,长度方向最小化。"""
    width: float = Field(..., gt=0, description="板宽 mm(排料定宽方向)")
    height: float | None = Field(None, description="板长 mm,留空则不限(strip 模式)")


class Placement(BaseModel):
    part_id: str
    rotation: float
    x: float
    y: float


class NestResult(BaseModel):
    placements: list[Placement]
    utilization: float = Field(..., description="材料利用率 0~1")
    used_length: float = Field(..., description="实际用到的板长 mm")
    sheet_width: float
    part_count: int
    run_time_sec: float


class Cut1DPiece(BaseModel):
    length: float
    qty: int


class Cut1DResult(BaseModel):
    bars: list[list[float]] = Field(..., description="每根原料上的切割长度列表")
    stock_length: float
    kerf: float
    utilization: float
    bar_count: int
    remnant: list[float] = Field(..., description="各原料余料长度")
