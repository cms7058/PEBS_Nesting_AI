"""阿米巴「平台令牌登录 + 按产品建计时项目 + 提交回传工时」（APS/Lean/worktime 同款）。

Nesting 无自有登录门禁，故无需铸会话：用户从阿米巴「重新接入/换令牌（带产品）」跳到本
工具 /register，核验平台令牌后按产品建一个排料作业计时项目（进入即自动开始计时），
前端操作页顶部内嵌计时横幅；提交时把排料作业工时回传到阿米巴该产品（/api/ingest/manhours）。

项目存本地 JSON（与会话同为 MVP 级；生产可换 DB）。
"""
from __future__ import annotations

import json
import secrets
import time
import urllib.request
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).resolve().parents[1] / "data"
_FILE = _DATA / "amiba_projects.json"
LABOR_RATE = 60.0  # ¥/h 默认工价
SCOPES = ["DXF 预处理与零件识别", "排样求解与共边优化", "余料调用核对", "出料表/NC 复核", "利用率与成本核算"]


# -- 持久化 --------------------------------------------------------------------

def _load() -> dict:
    try:
        return json.loads(_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")


def _now_sec() -> int:
    return int(time.time())


def _task_elapsed(t: dict) -> int:
    return t["active_seconds"] + (max(0, _now_sec() - t["running_since"]) if t["running_since"] else 0)


def project_dict(p: dict) -> dict:
    tasks = p.get("tasks", [])
    total = sum(_task_elapsed(t) for t in tasks)
    return {
        "id": p["id"], "enterpriseId": p["enterprise_id"], "enterpriseName": p["enterprise_name"],
        "productId": p["product_id"], "partNo": p["part_no"], "productName": p["product_name"],
        "laborRate": p["labor_rate"], "startedAt": p["started_at"], "submittedAt": p.get("submitted_at"),
        "status": p["status"], "totalSeconds": total,
        "manHours": round(total / 3600, 2), "laborCost": round(total / 3600 * p["labor_rate"], 2),
        "report": p.get("report"),
        "tasks": [{
            "id": t["id"], "assigneeUsername": t["assignee_username"], "assigneeDisplay": t["assignee_display"],
            "scope": t["scope"], "status": t["status"], "running": t["running_since"] is not None,
            "elapsedSeconds": _task_elapsed(t),
        } for t in tasks],
    }


# -- 出站调用阿米巴 ------------------------------------------------------------

def _post_json(url: str, body: dict, token: str = "") -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def verify_platform(amiba_endpoint: str, username: str, token: str, tool: str = "nesting") -> dict:
    """调阿米巴 /api/platform-auth/verify 核验平台令牌。"""
    try:
        _, data = _post_json(
            amiba_endpoint.rstrip("/") + "/api/platform-auth/verify",
            {"username": username, "token": token, "tool": tool})
        return data
    except Exception as e:
        return {"valid": False, "reason": f"无法连接阿米巴平台：{e}"}


def hello(amiba_endpoint: str, connector_token: str, capabilities: list, inbound_url: str = "") -> None:
    """登记接入时上报能力（已注册）。失败不阻断。"""
    try:
        _post_json(amiba_endpoint.rstrip("/") + "/api/connectors/hello",
                   {"version": "0.1.0", "capabilities": capabilities, "inboundUrl": inbound_url},
                   connector_token)
    except Exception:
        pass


# -- 计时项目 ------------------------------------------------------------------

def get_project(project_id: str) -> Optional[dict]:
    p = _load().get(project_id)
    return project_dict(p) if p else None


def ensure_project(*, enterprise_id: str, enterprise_name: str, product_id: str, part_no: str,
                   product_name: str, amiba_endpoint: str, connector_token: str,
                   created_by: str, team: Optional[list] = None) -> dict:
    """按产品找/建排料计时项目：已有进行中的则复用；否则新建并（单人）自动开始计时。"""
    projects = _load()
    for p in projects.values():
        if p["product_id"] == product_id and p["status"] == "active":
            return project_dict(p)

    members = team or [{"username": created_by or "me"}]
    solo = len(members) == 1
    pid = "nest_proj_" + secrets.token_hex(5)
    p = {
        "id": pid, "enterprise_id": enterprise_id, "enterprise_name": enterprise_name,
        "product_id": product_id, "part_no": part_no, "product_name": product_name,
        "amiba_endpoint": amiba_endpoint.rstrip("/"), "connector_token": connector_token,
        "labor_rate": LABOR_RATE, "created_by": created_by, "started_at": _now_sec(),
        "submitted_at": None, "status": "active", "report": None,
        "tasks": [{
            "id": "task_" + secrets.token_hex(4),
            "assignee_username": m["username"], "assignee_display": m.get("displayName") or m["username"],
            "scope": (SCOPES[i % len(SCOPES)] if len(members) > 1 else "整体排料作业"),
            "status": "doing" if solo else "todo", "active_seconds": 0,
            "running_since": _now_sec() if solo else None,
        } for i, m in enumerate(members)],
    }
    projects[pid] = p
    _save(projects)
    return project_dict(p)


def task_action(project_id: str, task_id: str, action: str) -> Optional[dict]:
    projects = _load()
    p = projects.get(project_id)
    if not p:
        return None
    t = next((x for x in p["tasks"] if x["id"] == task_id), None)
    if not t:
        raise ValueError("任务不存在")
    if action == "start":
        if not t["running_since"]:
            t["running_since"] = _now_sec()
            t["status"] = "doing"
    elif action == "stop":
        if t["running_since"]:
            t["active_seconds"] = _task_elapsed(t)
            t["running_since"] = None
    elif action == "done":
        t["active_seconds"] = _task_elapsed(t)
        t["running_since"] = None
        t["status"] = "done"
    else:
        raise ValueError("未知操作")
    _save(projects)
    return project_dict(p)


def submit_project(project_id: str) -> Optional[dict]:
    projects = _load()
    p = projects.get(project_id)
    if not p:
        return None
    if p["status"] == "submitted":
        return project_dict(p)

    members, total = [], 0
    for t in p["tasks"]:
        secs = _task_elapsed(t)
        t["active_seconds"] = secs
        t["running_since"] = None
        total += secs
        members.append({"username": t["assignee_username"], "seconds": secs})
    man_hours = round(total / 3600, 2)
    labor_cost = round(man_hours * p["labor_rate"], 2)

    report_ok, report_err = False, None
    if p["amiba_endpoint"] and p["connector_token"] and p["product_id"]:
        try:
            status, _ = _post_json(
                p["amiba_endpoint"].rstrip("/") + "/api/ingest/manhours",
                {"productId": p["product_id"], "manHours": man_hours, "laborCost": labor_cost,
                 "members": members,
                 "summary": f"排料作业工时 {man_hours}h · 人工成本 ¥{round(labor_cost)}"},
                p["connector_token"])
            report_ok = status in (200, 201)
            if not report_ok:
                report_err = f"HTTP {status}"
        except Exception as e:
            report_err = str(e)
    else:
        report_err = "缺少连接器令牌/产品，未回传"

    p["status"] = "submitted"
    p["submitted_at"] = _now_sec()
    p["report"] = {"ok": report_ok, "error": report_err, "manHours": man_hours, "laborCost": labor_cost}
    _save(projects)
    return project_dict(p)
