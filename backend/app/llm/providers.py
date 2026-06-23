"""LLM provider 适配 —— 可切换 Claude / Qwen3 / MiniMax 2.7 / GLM 5.2。

统一 chat(messages, tools) 接口,返回归一化的 (assistant_text, tool_calls, raw)。
Claude 走官方 anthropic SDK;Qwen/MiniMax/GLM 走各自 OpenAI 兼容端点。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.config import settings


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMReply:
    text: str
    tool_calls: list[ToolCall]
    raw: Any  # provider 原生 assistant 消息,供回灌历史


class BaseProvider:
    def chat(self, messages: list[dict], tools: list, system: str) -> LLMReply: ...
    def tool_result_message(self, call: ToolCall, result: dict) -> dict: ...
    def assistant_message(self, reply: LLMReply) -> dict: ...


# ---------------- Claude (Anthropic) ----------------

class ClaudeProvider(BaseProvider):
    def __init__(self, api_key: str, model: str):
        import anthropic
        from app.tools.registry import anthropic_schema
        self._client = anthropic.Anthropic(api_key=api_key)
        self._tools = anthropic_schema()
        self._model = model

    def chat(self, messages: list[dict], tools=None, system: str = "") -> LLMReply:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            thinking={"type": "adaptive"},  # Opus 4.8：自适应思考
            system=system,
            tools=self._tools,
            messages=messages,
        )
        text, calls = "", []
        for block in resp.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, args=block.input))
        return LLMReply(text=text, tool_calls=calls, raw=resp.content)

    def assistant_message(self, reply: LLMReply) -> dict:
        return {"role": "assistant", "content": reply.raw}

    def tool_result_message(self, call: ToolCall, result: dict) -> dict:
        return {"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": call.id,
            "content": json.dumps(result, ensure_ascii=False),
        }]}


# ---------------- OpenAI 兼容(Qwen / MiniMax / GLM）----------------

class OpenAICompatProvider(BaseProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        from openai import OpenAI
        from app.tools.registry import openai_schema
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._tools = openai_schema()
        self._model = model

    def chat(self, messages: list[dict], tools=None, system: str = "") -> LLMReply:
        msgs = [{"role": "system", "content": system}] + messages if system else messages
        resp = self._client.chat.completions.create(
            model=self._model, messages=msgs, tools=self._tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        calls = []
        for tc in (msg.tool_calls or []):
            calls.append(ToolCall(id=tc.id, name=tc.function.name,
                                  args=json.loads(tc.function.arguments or "{}")))
        return LLMReply(text=msg.content or "", tool_calls=calls, raw=msg)

    def assistant_message(self, reply: LLMReply) -> dict:
        m = reply.raw
        out: dict = {"role": "assistant", "content": m.content or ""}
        if m.tool_calls:
            out["tool_calls"] = [{
                "id": tc.id, "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            } for tc in m.tool_calls]
        return out

    def tool_result_message(self, call: ToolCall, result: dict) -> dict:
        return {"role": "tool", "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False)}


def get_provider(name: str | None = None) -> BaseProvider:
    from app import llm_config
    cfg = llm_config.load()
    name = (name or cfg["provider"]).lower()
    if name not in cfg["providers"]:
        raise ValueError(f"未知 provider: {name}")
    eff = cfg["providers"][name]
    if not eff["api_key"]:
        raise ValueError(f"provider「{name}」未配置 API key,请在页面右上「模型配置」中填写")
    if name == "claude":
        return ClaudeProvider(eff["api_key"], eff["model"])
    return OpenAICompatProvider(eff["api_key"], eff["base_url"], eff["model"])
