"""channels/session.py —— 会话归属：(渠道, 会话) → 稳定的 thread_id

同一个 (channel, conversation_id) 永远映射到同一个 thread_id，
这样：① 同一飞书群的连续对话能续上；② 不同渠道/不同群互不串台。
"""

import hashlib

from channels.base import InboundMessage

def thread_id_for(msg: InboundMessage, tenant_id: str = "default") -> str:
    """
    (租户, 渠道, 会话) → 稳定 thread_id。
    加入 tenant_id：多租户下，不同租户的会话彻底隔离。
    即便两个租户的 (channel, conversation_id) 偶然相同，thread 也不同。
    """
    raw = f"{tenant_id}:{msg.channel}:{msg.conversation_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

























