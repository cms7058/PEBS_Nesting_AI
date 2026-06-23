"""LLM 运行时配置(页面可配)—— 覆盖 .env 默认,持久化 JSON。

页面上配置各 provider 的 api_key / model / base_url 与默认 provider,
get_provider 读此覆盖层,空则回退 settings(.env)。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings

STORE = Path(__file__).resolve().parents[1] / "llm_config.json"

# 各 provider 的 .env 默认(作为回退与展示)
DEFAULTS = {
    "claude": {"model": settings.claude_model, "base_url": "", "api_key": settings.anthropic_api_key},
    "qwen": {"model": settings.qwen_model, "base_url": settings.qwen_base_url, "api_key": settings.qwen_api_key},
    "minimax": {"model": settings.minimax_model, "base_url": settings.minimax_base_url, "api_key": settings.minimax_api_key},
    "glm": {"model": settings.glm_model, "base_url": settings.glm_base_url, "api_key": settings.glm_api_key},
}


def load() -> dict:
    stored = json.loads(STORE.read_text()) if STORE.exists() else {}
    providers = {}
    for name, d in DEFAULTS.items():
        s = stored.get("providers", {}).get(name, {})
        providers[name] = {
            "api_key": s.get("api_key") or d["api_key"],
            "model": s.get("model") or d["model"],
            "base_url": s.get("base_url") or d["base_url"],
        }
    return {"provider": stored.get("provider") or settings.llm_provider, "providers": providers}


def effective(name: str) -> dict:
    return load()["providers"][name]


def save(cfg: dict) -> None:
    STORE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def update(provider: str | None, configs: dict[str, dict] | None) -> dict:
    """provider:设默认;configs:{name:{api_key?,model?,base_url?}} 部分更新。"""
    cur = json.loads(STORE.read_text()) if STORE.exists() else {"providers": {}}
    if provider:
        cur["provider"] = provider
    if configs:
        cur.setdefault("providers", {})
        for name, c in configs.items():
            slot = cur["providers"].setdefault(name, {})
            for k in ("api_key", "model", "base_url"):
                if k in c and c[k] is not None:
                    slot[k] = c[k]
    save(cur)
    return load()


def masked() -> dict:
    """返回给前端:key 用是否已配置代替,不回传明文。"""
    cfg = load()
    out = {"provider": cfg["provider"], "providers": {}}
    for name, p in cfg["providers"].items():
        out["providers"][name] = {
            "model": p["model"], "base_url": p["base_url"],
            "key_set": bool(p["api_key"]),
        }
    return out
