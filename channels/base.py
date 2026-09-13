
"""channels/base.py —— 渠道统一抽象

每个渠道（飞书/CLI/Web/Webhook）把自己的原始消息翻译成 InboundMessage，
把 agent 的结果通过 ChannelAdapter.send 翻译回自己的格式。
核心业务只认 InboundMessage / 统一结果，不关心消息来自哪个渠道。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class InboundMessage:
    """归一化的入站消息————所有渠道翻译成它。"""
    channel:str
    user_id:str
    text:str
    conversation_id:str
    raw: dict | None = None


class ChannelAdapter(ABC):
    """渠道适配器接口：把渠道接入收敛成统一的两件事。"""

    name: str = "base"

    @abstractmethod
    async def send(self, conversation_id: str, text: str) -> None:
        """把回复发回该渠道的制定会话。"""

        # ···





























