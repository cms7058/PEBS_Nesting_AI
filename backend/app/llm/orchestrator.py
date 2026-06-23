"""对话编排 —— Function Calling 循环。

LLM 理解意图 → 调用工具(求解器）→ 用工具结果继续解释,直到无更多工具调用。
provider 无关:同一循环驱动 Claude / Qwen / MiniMax / GLM。
"""
from __future__ import annotations

from app.llm.providers import BaseProvider, get_provider
from app.tools.registry import Session, dispatch

SYSTEM_PROMPT = """你是「智能排料 Copilot」,帮中小钣金/机械加工厂用对话完成下料排料。
规则:
- 用户用自然语言描述需求(料型、定尺、零件、数量、锯缝等),你抽取参数并调用工具计算。
- 你绝不自己心算排料/利用率,必须调用 cut_1d / nest_2d 等工具,确保结果可验证。
- 拿到工具结果后,用简洁中文解释方案(利用率、用料根数/板长、余料),并主动提示下一步(如导出 NC、换定尺重算)。
- 二维排料需用户先上传 DXF;若未载入零件,提示上传。
"""

MAX_STEPS = 6


def chat_once(session: Session, history: list[dict], user_text: str,
              provider_name: str | None = None) -> tuple[str, list[dict]]:
    """处理一轮用户输入,返回(最终回复文本, 更新后的 history)。"""
    provider: BaseProvider = get_provider(provider_name)
    history = history + [{"role": "user", "content": user_text}]

    for _ in range(MAX_STEPS):
        reply = provider.chat(history, tools=None, system=SYSTEM_PROMPT)
        history.append(provider.assistant_message(reply))
        if not reply.tool_calls:
            return reply.text, history
        for call in reply.tool_calls:
            result = dispatch(call.name, call.args, session)
            history.append(provider.tool_result_message(call, result))
    return "(已达最大工具调用步数,请细化需求)", history
