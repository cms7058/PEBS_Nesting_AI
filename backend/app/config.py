"""配置：引擎路径与各 LLM provider 凭证。"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # Nesting_Copilot/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # sparrow 引擎(第零阶段已构建)—— 条带模式(定宽、开口长度)
    sparrow_bin: str = str(ROOT / "phase0/engines/sparrow/target/release/sparrow")
    nest_time_sec: int = 20  # 单次排料求解时限
    # bin_nester 引擎 —— 固定尺寸板材、多张、按需求量装箱(方案乙)
    bin_nester_bin: str = str(ROOT / "phase0/engines/bin_nester/target/release/bin_nester")

    # LLM provider 默认
    llm_provider: str = "claude"  # claude | qwen | minimax | glm

    # Claude (Anthropic)
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-4-8"

    # OpenAI 兼容(Qwen3 / MiniMax 2.7 / GLM 5.2 均走 OpenAI 兼容协议)
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3-max"

    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.chat/v1"
    minimax_model: str = "minimax-2.7"

    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-5.2"

    # PEBS 阿米巴成本闭环(料要素上报)
    amiba_endpoint: str = ""          # 主阿米巴地址,空=独立模式(连接器休眠)
    amiba_token: str = ""
    amiba_enterprise_id: str = ""
    amiba_source: str = "nesting"
    amiba_sync_mode: str = "off"      # off | push


settings = Settings()
