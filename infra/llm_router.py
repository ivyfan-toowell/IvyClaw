"""infra/llm_router.py —— 多模型路由（统一抽象 + 按档位选 + 配置化）

工程化要点：
- 模型注册表来自配置（settings.model_tiers），增减/调整不改业务代码；
- 业务代码按"逻辑档位"取模型（get_model("strong") / get_model_for_role("coder")），
  不直接写模型名——换模型只改配置；
- 缓存已构造的模型对象，避免重复构造；
- 预留 fallback 协调点（第 11 章用）。
"""

from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model

from infra.settings import get_settings
from infra.logging import get_logger

logger = get_logger()


ROLE_TO_TIER: dict[str, str] = {
    "main": "strong",
    "planner": "strong",
    "researcher": "cheap",
    "coder": "strong",
    "tester": "standard",
    "reviewer": "strong",
}

@lru_cache(maxsize=None)
def _build(model_name: str):
    """按模型名构造一个 chat model（带缓存）。统一走 OpenAI 兼容接口 + base_url。"""
    s = get_settings()
    logger.info("构造模型：{}", model_name)
    return init_chat_model(
        model=model_name,
        model_provider=s.model_provider,
        api_key=s.api_key.get_secret_value(),
        base_url=s.base_url,
        temperature=0,
        max_retries=s.max_retries,
        timeout=s.timeout,
    )

def get_model(tier: str = "strong"):
    """按档位取模型对象。tier ∈ settings.model_tiers（strong/standard/cheap）。"""
    tiers = get_settings().model_tiers
    if tier not in tiers:
        raise KeyError(f"未知模型档位：{tier}，可选：{list(tiers)}")
    return _build(tiers[tier])

def get_model_for_role(role: str):
    """按角色取模型（用于子代理）。role 如 planner/coder/researcher…"""
    tier = ROLE_TO_TIER.get(role,"strong")
    return get_model(tier)


























