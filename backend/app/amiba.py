"""PEBS 阿米巴成本闭环连接器(料要素)——排料 → 成本 → 经营。

把排料/下料结果折算成阿米巴统一中间模型(FactorMetric 料要素指标 + WasteItem 浪费项),
POST 到主阿米巴 /api/ingest。零硬依赖:未配 AMIBA_ENDPOINT 即独立模式,只返回预览不外发。
数据契约见 app/src/lib/factory-types.ts。
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

from app.config import settings

DEFAULT_BENCHMARK = 88.0  # 行业基准利用率(SigmaNEST 级),供利用率损失归因


def enabled() -> bool:
    return bool(settings.amiba_endpoint) and settings.amiba_sync_mode == "push"


def build_envelope(*, kind: str, material: str, util_pct: float, benchmark: float,
                   input_weight: float, product_weight: float, recoverable_weight: float,
                   unit_price: float, cutting_min: float, batch_id: str) -> dict:
    """构建 ingest 信封(料要素指标 + 成本浪费项 + 切割工时)。"""
    now = datetime.now(timezone.utc).isoformat()
    src = settings.amiba_source
    waste_weight = max(input_weight - product_weight - recoverable_weight, 0.0)
    waste_cost = round(waste_weight * unit_price, 2)
    material_cost = round(input_weight * unit_price, 2)

    metrics = [
        {"factor": "material", "key": "nesting_yield",
         "label": f"{'板材' if kind == 'sheet' else '型材'}套料利用率",
         "value": round(util_pct, 1), "unit": "%", "benchmark": benchmark,
         "source": src, "capturedAt": now},
        {"factor": "material", "key": "material_cost",
         "label": "投入材料成本", "value": material_cost, "unit": "元",
         "source": src, "capturedAt": now},
        {"factor": "material", "key": "remnant_reuse",
         "label": "可复用余料(资产)", "value": round(recoverable_weight, 1), "unit": "kg",
         "source": src, "capturedAt": now},
        {"factor": "machine", "key": "cutting_time",
         "label": "切割工时", "value": round(cutting_min, 1), "unit": "min",
         "source": src, "capturedAt": now},
    ]

    waste_items = []
    if util_pct < benchmark and waste_cost > 0:
        waste_items.append({
            "factor": "material", "threeProps": "rationality",
            "description": f"{material} 套料利用率 {util_pct:.1f}% 低于基准 {benchmark:.0f}%,"
                           f"浪费料 {waste_weight:.1f}kg",
            "annualCost": waste_cost,
            "costAccount": "材料利用率损失",
            "attributionRule": "排料利用率差额归制造阿米巴",
            "source": src,
        })

    return {
        "source": src,
        "enterpriseId": settings.amiba_enterprise_id,
        "batchId": batch_id,
        "schemaVersion": "v2",
        "metrics": metrics,
        "wasteItems": waste_items,
    }


def push(envelope: dict) -> dict:
    """推送到主阿米巴(push 模式);独立模式返回跳过。失败只回错误不抛(不影响本系统)。"""
    if not enabled():
        return {"skipped": True, "reason": "独立模式(未配置 AMIBA_ENDPOINT 或 AMIBA_SYNC_MODE≠push)"}
    try:
        req = urllib.request.Request(
            f"{settings.amiba_endpoint}/api/ingest",
            data=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {settings.amiba_token}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"pushed": True, "response": json.loads(resp.read().decode("utf-8"))}
    except Exception as e:
        return {"pushed": False, "error": str(e)}
