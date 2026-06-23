"""智能排料 Copilot —— FastAPI 后端(第一阶段板材 MVP）。

闭环:上传 DXF → 对话排料(LLM + 工具）→ 排料图/NC 导出。
内存级会话存储(MVP；生产换 Redis/PG)。
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.geometry.dxf import parse_dxf
from app.llm.orchestrator import chat_once
from app.output.export import to_dxf_text, to_nc, to_svg
from app.tools.registry import Session

app = FastAPI(title="Nesting Copilot", version="0.1.0")

# 会话存储(MVP 内存级）
SESSIONS: dict[str, Session] = {}
HISTORIES: dict[str, list[dict]] = {}


def _get(sid: str) -> Session:
    if sid not in SESSIONS:
        raise HTTPException(404, "会话不存在,请先 POST /session")
    return SESSIONS[sid]


@app.post("/session")
def create_session() -> dict:
    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = Session()
    HISTORIES[sid] = []
    return {"session_id": sid}


@app.post("/session/{sid}/upload")
async def upload_dxf(sid: str, file: UploadFile = File(...), clean: bool = True) -> dict:
    """上传 DXF。clean=true(默认)走脏数据预处理(轮廓重组/缺口修复/剔折弯线/识孔),
    返回诊断;失败或无结果回退简单解析(仅闭合多段线)。"""
    from app.geometry.clean_dxf import clean_dxf
    session = _get(sid)
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    diag = None
    try:
        parts = []
        if clean:
            try:
                parts, diag = clean_dxf(path)
            except Exception as e:
                diag = {"error": str(e)}
        if not parts:
            parts = parse_dxf(path)  # 回退:仅闭合 LWPOLYLINE
            if diag is None:
                diag = {"mode": "simple"}
    finally:
        Path(path).unlink(missing_ok=True)
    session.parts = parts
    return {"loaded_parts": len(parts), "part_ids": [p.id for p in parts][:50],
            "diagnostics": diag}


class ChatIn(BaseModel):
    message: str
    provider: str | None = None  # claude | qwen | minimax | glm


@app.post("/session/{sid}/chat")
def chat(sid: str, body: ChatIn) -> dict:
    session = _get(sid)
    reply, history = chat_once(session, HISTORIES[sid], body.message, body.provider)
    HISTORIES[sid] = history
    out: dict = {"reply": reply}
    if session.last_nest is not None:
        out["nest"] = {
            "utilization": session.last_nest.utilization,
            "placed": session.last_nest.part_count,
            "used_length_mm": session.last_nest.used_length,
        }
    return out


class NestIn(BaseModel):
    sheet_width_mm: float
    time_sec: int | None = None


@app.post("/session/{sid}/nest")
def run_nest(sid: str, body: NestIn) -> dict:
    """直接触发二维排料(供交互画布,绕过对话)。"""
    from app.engine.sparrow_engine import nest_2d
    from app.schemas import Sheet
    session = _get(sid)
    if not session.parts:
        raise HTTPException(400, "尚未载入零件,请先上传 DXF")
    session.last_nest = nest_2d(session.parts, Sheet(width=body.sheet_width_mm),
                                time_sec=body.time_sec)
    return layout(sid)


class SheetNestIn(BaseModel):
    sheet_length_mm: float           # 板材长(mm)
    sheet_width_mm: float            # 板材宽(mm)
    sheet_count: int = 100           # 可用张数
    demands: dict[str, int] = {}     # {part_id: 所需数量};留空则用各零件 demand
    use_remnants: bool = False       # 是否优先使用余料库中的可用余料
    material: str = "Q235"           # 材料牌号
    thickness_mm: float = 0.0        # 板厚(算重量用,必填才有重量核算)


@app.post("/session/{sid}/nest_sheets")
def nest_sheets_ep(sid: str, body: SheetNestIn) -> dict:
    """固定尺寸板材 + 多张 + 按需求量装箱,返回出料表(方案乙)。"""
    from app import remnant
    from app.engine.bin_nester import nest_sheets
    from app.materials import density_for
    session = _get(sid)
    if not session.parts:
        raise HTTPException(400, "尚未载入零件,请先上传 DXF")

    rem_bins = []
    if body.use_remnants:
        for r in remnant.list_remnants():
            # 2D 复用须同牌号 + 同板厚
            if (r.get("kind", "2d") == "2d" and r.get("status") == "available"
                    and r.get("material") == body.material
                    and abs(r.get("thickness", 0) - body.thickness_mm) < 0.05):
                lr = r["largest_rect"]
                if lr["w"] > 0 and lr["h"] > 0:
                    rem_bins.append({"id": r["id"], "w": lr["w"], "h": lr["h"]})

    result = nest_sheets(session.parts, body.demands, body.sheet_length_mm,
                         body.sheet_width_mm, body.sheet_count, remnants=rem_bins)
    result["spec"] = {"material": body.material, "thickness": body.thickness_mm}
    if body.thickness_mm > 0:
        from shapely.geometry import Polygon
        d = density_for(body.material)
        # 净产品面积扣除内孔(孔是冲掉的废料,不计入净产品重量)
        hole_area = {p.id: sum(Polygon(h).area for h in (p.holes or [])) for p in session.parts}
        prod_area = sum(max(Polygon(p["points"]).area - hole_area.get(p["part_id"], 0), 0)
                        for sh in result["sheets"] for p in sh.get("items", []))
        new_area = sum(sh["width"] * sh["height"] for sh in result["sheets"] if not sh["is_remnant"])
        result["accounting"] = {
            "thickness_mm": body.thickness_mm,
            "weight_kg_per_m2": round(body.thickness_mm * d * 1e6, 2),
            "product_weight_kg": round(prod_area * body.thickness_mm * d, 2),
            "input_weight_kg": round(new_area * body.thickness_mm * d, 2),
            "remnant_weight_kg": round(max(new_area - prod_area, 0) * body.thickness_mm * d, 2),
        }
    session.last_sheets = result
    return result


class RegisterIn(BaseModel):
    min_free_ratio: float = 0.15     # 仅登记自由率≥此阈值的板(过滤几乎排满的板)


@app.post("/session/{sid}/register_remnants")
def register_remnants_ep(sid: str, body: RegisterIn) -> dict:
    """从最近一次出料表,把各板余料(含规格/牌号/重量)登记入余料库。"""
    from app import remnant
    from app.materials import density_for
    session = _get(sid)
    if not session.last_sheets:
        raise HTTPException(400, "尚无出料表,请先生成排版")
    spec = session.last_sheets.get("spec", {})
    material = spec.get("material", "Q235")
    thickness = spec.get("thickness", 0)
    density = density_for(material)
    registered = []
    for sh in session.last_sheets["sheets"]:
        info = remnant.extract_remnant(
            sh["width"], sh["height"], [it["points"] for it in sh["items"]])
        if info["free_ratio"] >= body.min_free_ratio:
            weight = round(info["free_area"] * thickness * density, 2) if thickness > 0 else 0.0
            registered.append(remnant.register(sh["sheet_code"], material,
                {"kind": "2d", "thickness": thickness, "weight_kg": weight, **info}))
    return {"registered": len(registered), "remnants": registered}


# ---------------- 管材/棒材一维下料(1D)----------------

class BarPiece(BaseModel):
    length_mm: float
    qty: int


class BarNestIn(BaseModel):
    pieces: list[BarPiece]
    stock_length_mm: float
    stock_count: int = 100
    kerf_mm: float = 0.0
    use_remnants: bool = False
    profile_type: str = "tube"       # tube(管材)| bar(棒材)
    od_mm: float = 0.0               # 外径
    thickness_mm: float = 0.0        # 壁厚(管材)
    material: str = "20#钢"          # 材料牌号


def _spec_match(r: dict, profile_type: str, od: float, thickness: float,
                material: str, tol: float = 0.5) -> bool:
    """余料规格是否匹配:同牌号、同料型、同外径;管材还需同壁厚(容差 tol)。"""
    if r.get("material") != material:
        return False
    if r.get("profile_type") != profile_type:
        return False
    if abs(r.get("od", -1) - od) > tol:
        return False
    if profile_type == "tube" and abs(r.get("thickness", -1) - thickness) > tol:
        return False
    return True


@app.post("/session/{sid}/nest_bars")
def nest_bars_ep(sid: str, body: BarNestIn) -> dict:
    """管材/棒材一维下料,返回切割出料表 + 规格重量核算。"""
    from app import remnant
    from app.engine.bar_cutting import accounting, nest_bars
    from app.materials import density_for
    session = _get(sid)
    rem_bars = []
    if body.use_remnants:
        for r in remnant.list_remnants():
            if (r.get("kind") == "1d" and r.get("status") == "available"
                    and r.get("length", 0) > 0
                    and _spec_match(r, body.profile_type, body.od_mm, body.thickness_mm, body.material)):
                rem_bars.append({"id": r["id"], "length": r["length"]})
    result = nest_bars([(p.length_mm, p.qty) for p in body.pieces],
                       body.stock_length_mm, body.stock_count, body.kerf_mm, rem_bars)
    result["spec"] = {"profile_type": body.profile_type, "od": body.od_mm,
                      "thickness": body.thickness_mm, "material": body.material}
    if body.od_mm > 0:
        result["accounting"] = accounting(result, body.profile_type, body.od_mm,
                                          body.thickness_mm, density_for(body.material))
    session.last_bars = result
    return result


class RegisterBarIn(BaseModel):
    min_remnant_mm: float = 200.0    # 仅登记余料长度≥此阈值的原料


@app.post("/session/{sid}/register_bar_remnants")
def register_bar_remnants_ep(sid: str, body: RegisterBarIn) -> dict:
    """从最近一次一维切割单,把各原料余料(含规格/牌号/重量)登记入余料库。"""
    from app import remnant
    from app.engine.bar_cutting import section_area
    from app.materials import density_for
    session = _get(sid)
    if not session.last_bars:
        raise HTTPException(400, "尚无切割单,请先生成下料")
    spec = session.last_bars.get("spec", {})
    material = spec.get("material", "20#钢")
    area = section_area(spec.get("profile_type", "tube"), spec.get("od", 0), spec.get("thickness", 0))
    density = density_for(material)
    registered = []
    for b in session.last_bars["bars"]:
        rl = b["remnant_length"]
        if rl >= body.min_remnant_mm:
            registered.append(remnant.register(
                b["bar_code"], material,
                {"kind": "1d", "length": rl, "free_ratio": round(rl / b["stock_length"], 4),
                 "profile_type": spec.get("profile_type", "tube"),
                 "od": spec.get("od", 0), "thickness": spec.get("thickness", 0),
                 "weight_kg": round(rl * area * density, 2)}))
    return {"registered": len(registered), "remnants": registered}


@app.get("/remnants")
def remnants_ep(kind: str | None = None) -> dict:
    from app import remnant
    items = remnant.list_remnants()
    if kind:
        items = [r for r in items if r.get("kind") == kind]
    return {"remnants": items}


@app.delete("/remnants/{rid}")
def del_remnant_ep(rid: str) -> dict:
    from app import remnant
    return {"deleted": remnant.delete(rid)}


@app.get("/session/{sid}/layout")
def layout(sid: str) -> dict:
    """返回排料后各零件的多边形(板坐标)与面积,供 Konva 交互渲染。"""
    from app.output.export import _placed_polygons
    session = _get(sid)
    if session.last_nest is None:
        raise HTTPException(400, "尚无排料结果")
    res = session.last_nest
    # sparrow 输出:固定维(板宽)在 Y、最小化长度在 X。展示层交换为「X=板宽，Y=长度」直觉坐标。
    parts = []
    for pid, poly in _placed_polygons(session.parts, res):
        parts.append({
            "id": pid,
            "points": [[round(y, 2), round(x, 2)] for x, y in poly.exterior.coords],
            "area": round(poly.area, 2),
        })
    return {"sheet_width": res.sheet_width, "used_length": round(res.used_length, 1),
            "utilization": res.utilization, "parts": parts}


@app.get("/session/{sid}/export/{fmt}")
def export(sid: str, fmt: str):
    session = _get(sid)
    if session.last_nest is None:
        raise HTTPException(400, "尚无排料结果,请先完成一次二维排料")
    if fmt == "svg":
        return PlainTextResponse(to_svg(session.parts, session.last_nest),
                                 media_type="image/svg+xml")
    if fmt == "nc":
        return PlainTextResponse(to_nc(session.parts, session.last_nest),
                                 media_type="text/plain")
    if fmt == "dxf":
        return PlainTextResponse(to_dxf_text(session.parts, session.last_nest),
                                 media_type="application/dxf")
    raise HTTPException(400, "fmt 仅支持 svg|nc|dxf")


@app.get("/session/{sid}/report")
def export_report_ep(sid: str, kind: str, fmt: str):
    """导出出料表/切割单。kind=sheet|bar;fmt=xlsx|pdf(打印HTML)。"""
    from fastapi.responses import HTMLResponse, Response

    from app import export_report
    session = _get(sid)
    result = session.last_sheets if kind == "sheet" else session.last_bars
    if not result:
        raise HTTPException(400, "尚无可导出的结果,请先生成排版/下料")

    if fmt == "xlsx":
        data = (export_report.sheet_xlsx(result) if kind == "sheet"
                else export_report.bar_xlsx(result))
        name = "板材出料表.xlsx" if kind == "sheet" else "型材切割单.xlsx"
        from urllib.parse import quote
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
    if fmt == "pdf":
        html = (export_report.sheet_html(result) if kind == "sheet"
                else export_report.bar_html(result))
        return HTMLResponse(html)  # 前端新窗口打开 → 浏览器打印为 PDF
    raise HTTPException(400, "fmt 仅支持 xlsx | pdf")


@app.get("/demo.dxf")
def demo_dxf():
    """生成一张含混合矩形件的示例 DXF,供「试用样例」与演示。"""
    import io
    import random

    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    rng = random.Random(7)
    for _ in range(14):
        w, h = rng.uniform(60, 180), rng.uniform(40, 120)
        msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True)
    buf = io.StringIO()
    doc.write(buf)
    return PlainTextResponse(buf.getvalue(), media_type="application/dxf")


class PushAmibaIn(BaseModel):
    kind: str                          # sheet(板材)| bar(管/棒)
    unit_price_per_kg: float = 5.0     # 材料单价 元/kg
    benchmark: float = 88.0            # 基准利用率 %
    sec_per_cut: float = 5.0           # 一维:每刀工时秒
    cut_speed_mm_min: float = 2000.0   # 二维:切割速度 mm/min


@app.post("/session/{sid}/push_amiba")
def push_amiba_ep(sid: str, body: PushAmibaIn) -> dict:
    """把最近一次排料/下料结果折算成本+工时,上报阿米巴(料要素)。独立模式返回预览。"""
    import time

    from shapely.geometry import Polygon

    from app import amiba
    session = _get(sid)

    if body.kind == "sheet":
        res = session.last_sheets
        if not res or "accounting" not in res:
            raise HTTPException(400, "尚无板材出料表或未填板厚(无重量核算)")
        acc = res["accounting"]
        material = res.get("spec", {}).get("material", "Q235")
        util = res["overall_utilization"] * 100
        # 切割工时:总零件周长 / 切割速度
        perim = sum(Polygon(p["points"]).length for sh in res["sheets"] for p in sh.get("items", []))
        cutting_min = perim / body.cut_speed_mm_min
        cost = dict(input_weight=acc["input_weight_kg"], product_weight=acc["product_weight_kg"],
                    recoverable_weight=acc.get("remnant_weight_kg", 0.0))
    elif body.kind == "bar":
        res = session.last_bars
        if not res or "accounting" not in res:
            raise HTTPException(400, "尚无型材切割单或未填外径(无重量核算)")
        acc = res["accounting"]
        material = res.get("spec", {}).get("material", "20#钢")
        util = res["overall_utilization"] * 100
        cuts = sum(c for b in res["bars"] for c in b["cuts"].values())
        cutting_min = cuts * body.sec_per_cut / 60.0
        cost = dict(input_weight=acc["input_weight_kg"], product_weight=acc["product_weight_kg"],
                    recoverable_weight=acc.get("remnant_weight_kg", 0.0))
    else:
        raise HTTPException(400, "kind 仅支持 sheet | bar")

    envelope = amiba.build_envelope(
        kind=body.kind, material=material, util_pct=util, benchmark=body.benchmark,
        input_weight=cost["input_weight"], product_weight=cost["product_weight"],
        recoverable_weight=cost["recoverable_weight"], unit_price=body.unit_price_per_kg,
        cutting_min=cutting_min, batch_id=f"nesting_{int(time.time())}")
    result = amiba.push(envelope)
    return {"envelope": envelope, "push_result": result, "amiba_enabled": amiba.enabled()}


# -- 阿米巴：平台令牌登录 + 按产品建计时项目 + 提交回传工时（APS/Lean/worktime 同款）-------

_NEST_CAPS = ["套料利用率", "共边/共线", "余料再利用", "利用率损失成本"]


class AmibaRegisterIn(BaseModel):
    amiba_endpoint: str
    amiba_token: str
    enterprise_id: str
    source: str = "nesting"


@app.post("/amiba/register")
def amiba_register(body: AmibaRegisterIn) -> dict:
    """阿米巴「接入」带来的连接器令牌：回 hello 上报能力（点亮已注册）。"""
    from app import amiba_projects
    amiba_projects.hello(body.amiba_endpoint, body.amiba_token, _NEST_CAPS)
    return {"ok": True, "enterprise_id": body.enterprise_id}


class AmibaPlatformLoginIn(BaseModel):
    amiba_endpoint: str
    platform_token: str
    username: str
    tool: str = "nesting"
    enterprise_id: str = ""


@app.post("/amiba/platform-login")
def amiba_platform_login(body: AmibaPlatformLoginIn) -> dict:
    """仅核验平台令牌（Nesting 无登录门禁，核验通过即放行）。"""
    from app import amiba_projects
    res = amiba_projects.verify_platform(body.amiba_endpoint, body.username, body.platform_token, body.tool)
    if not res.get("valid"):
        raise HTTPException(401, res.get("reason") or "平台令牌核验失败")
    return {"ok": True, "displayName": res.get("displayName") or body.username}


class AmibaLaunchIn(BaseModel):
    amiba_endpoint: str
    platform_token: str
    username: str
    tool: str = "nesting"
    enterprise_id: str
    enterprise_name: str = ""
    product_id: str
    part_no: str = ""
    product_name: str = ""
    connector_token: str = ""
    team: list = []


@app.post("/amiba/launch")
def amiba_launch(body: AmibaLaunchIn) -> dict:
    """核验平台令牌 → 按产品建排料计时项目（单人进入即自动开始计时）。"""
    from app import amiba_projects
    res = amiba_projects.verify_platform(body.amiba_endpoint, body.username, body.platform_token, body.tool)
    if not res.get("valid"):
        raise HTTPException(401, res.get("reason") or "平台令牌核验失败")
    project = amiba_projects.ensure_project(
        enterprise_id=body.enterprise_id, enterprise_name=body.enterprise_name,
        product_id=body.product_id, part_no=body.part_no, product_name=body.product_name,
        amiba_endpoint=body.amiba_endpoint, connector_token=body.connector_token,
        created_by=body.username, team=body.team)
    return {"ok": True, "projectId": project["id"], "productName": body.product_name,
            "partNo": body.part_no, "enterpriseName": body.enterprise_name}


@app.get("/amiba/projects/{project_id}")
def amiba_get_project(project_id: str) -> dict:
    from app import amiba_projects
    p = amiba_projects.get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


@app.post("/amiba/projects/{project_id}/tasks/{task_id}/{action}")
def amiba_task_action(project_id: str, task_id: str, action: str) -> dict:
    from app import amiba_projects
    if action not in ("start", "stop", "done"):
        raise HTTPException(400, "未知操作")
    try:
        p = amiba_projects.task_action(project_id, task_id, action)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


@app.post("/amiba/projects/{project_id}/submit")
def amiba_submit_project(project_id: str) -> dict:
    from app import amiba_projects
    p = amiba_projects.submit_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


class LLMConfigIn(BaseModel):
    provider: str | None = None                  # 设默认 provider
    configs: dict[str, dict] | None = None        # {name: {api_key?, model?, base_url?}}


@app.get("/config/llm")
def get_llm_config() -> dict:
    from app import llm_config
    return llm_config.masked()


@app.post("/config/llm")
def set_llm_config(body: LLMConfigIn) -> dict:
    from app import llm_config
    llm_config.update(body.provider, body.configs)
    return llm_config.masked()


@app.get("/demo_dirty.dxf")
def demo_dirty_dxf():
    """脏 DXF 示例:散乱 LINE+ARC 拼的圆角件 + 内孔 + 折弯线层 + 文字标注,演示预处理。"""
    import io

    import ezdxf
    doc = ezdxf.new("R2010")
    doc.layers.add("BEND", color=1)
    msp = doc.modelspace()
    # 圆角矩形(散乱直线+圆弧)+ 内孔
    msp.add_line((10, 0), (90, 0)); msp.add_line((100, 10), (100, 50))
    msp.add_line((90, 60), (10, 60)); msp.add_line((0, 50), (0, 10))
    msp.add_arc((90, 10), 10, 270, 360); msp.add_arc((90, 50), 10, 0, 90)
    msp.add_arc((10, 50), 10, 90, 180); msp.add_arc((10, 10), 10, 180, 270)
    msp.add_circle((50, 30), 8)
    msp.add_line((20, 30), (80, 30), dxfattribs={"layer": "BEND"})  # 折弯线
    # 独立矩形 + 文字标注
    msp.add_lwpolyline([(150, 0), (230, 0), (230, 50), (150, 50)], close=True)
    msp.add_text("PART-2", dxfattribs={"layer": "BEND"}).set_placement((160, 20))
    buf = io.StringIO(); doc.write(buf)
    return PlainTextResponse(buf.getvalue(), media_type="application/dxf")


@app.get("/health")
def health() -> dict:
    from app.config import settings
    return {"ok": True, "sparrow": Path(settings.sparrow_bin).exists(),
            "default_provider": settings.llm_provider}
