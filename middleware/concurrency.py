"""
middleware/concurrency.py —— 在 LLM 调用层限并发（精确粒度）

asyncio.Semaphore(N)：同时进行的 LLM 调用不超过 N 个,多的排队。
放在 awrap_model_call 里,比包整个 ainvoke 精确——后者只能限"并发 agent 数"。
"""
import asyncio
from collections.abc import Callable

from langchain.agents.middleware import (
    AgentMiddleware, ModelRequest, ModelResponse,
)

from infra.settings import get_settings

# 进程级 LLM 并发闸(别超过模型厂商的并发配额)
_llm_sem = asyncio.Semaphore(get_settings().max_concurrent_llm)


class LLMConcurrencyMiddleware(AgentMiddleware):
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        async with _llm_sem:                 # ← 真正卡住并发 LLM 调用
            return await handler(request)



