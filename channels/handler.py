"""各渠道统一的身份隔离、调度与记忆处理入口。"""
from typing import Any
from app.memory import MemoryService

from agent.dispatcher import _last_message_text, run_issue
from channels.base import InboundMessage
from channels.session import thread_id_for
from infra.logging import get_logger

logger = get_logger()


async def handle_message(
    msg: InboundMessage, checkpointer: Any, store: Any, tenant_id: str = "default", redis: Any = None,
) -> str:
    """为归一化消息调用显式 dispatcher，复用持久化资源。"""
    thread_id = thread_id_for(msg, tenant_id)
    logger.info("处理消息：channel={} user={} thread={} chars={}", msg.channel, msg.user_id, thread_id, len(msg.text))
    memory = MemoryService(store, msg.user_id, tenant_id, msg.channel, redis=redis) if store is not None else None
    memory_context = await memory.context(msg.conversation_id, msg.text) if memory else ""
    result = await run_issue(msg.text, thread_id=thread_id, checkpointer=checkpointer, store=store,
                             user_id=msg.user_id, channel=msg.channel,
                             memory_context=memory_context, memory_service=memory, user_text=msg.text)
    reply = _last_message_text(result)
    if memory:
        await memory.record_turn(msg.conversation_id, msg.text, reply)
    return reply






















