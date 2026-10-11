"""统一解析飞书纯文本和富文本消息，并可靠入队。"""
import asyncio
import json
from typing import Any

from channels.base import InboundMessage
from channels.feishu import FeishuChannel
from infra.logging import get_logger
from tasks.queue import enqueue_issue

logger = get_logger()


def parse_feishu_message(message: dict[str, Any], sender: dict[str, Any]) -> InboundMessage | None:
    """提取 text/post 中的普通文本和代码块，记录无法处理的消息。"""
    if sender.get("sender_type") == "app":
        return None
    kind = message.get("message_type")
    try:
        content = json.loads(message.get("content") or "{}")
        if kind == "text":
            text = content.get("text", "")
        elif kind == "post":
            post = content if "content" in content else content.get("zh_cn", content.get("en_us", {}))
            parts = [post.get("title", "")]
            for row in post.get("content", []):
                parts.append("".join(node.get("text", "") for node in row
                                     if node.get("tag") in {"text", "a", "code_block"}))
            text = "\n".join(parts)
        else:
            logger.info("忽略飞书消息类型：{} message={}", kind, message.get("message_id"))
            return None
    except (json.JSONDecodeError, TypeError, AttributeError):
        logger.warning("飞书消息内容格式错误：message={}", message.get("message_id"))
        return None
    user_id = (sender.get("sender_id") or {}).get("open_id")
    chat_id = message.get("chat_id")
    if not isinstance(text, str) or not text.strip() or not user_id or not chat_id:
        logger.info("忽略飞书无有效文本或标识的消息：type={} message={}", kind, message.get("message_id"))
        return None
    return InboundMessage(channel="feishu", user_id=user_id, text=text.strip(), conversation_id=chat_id)


async def enqueue_feishu(redis: Any, inbound: InboundMessage, message_id: str) -> str:
    """先持久入队再回执；message_id 提供跨进程幂等。"""
    if not message_id:
        raise ValueError("飞书消息缺少 message_id")
    job_id = await enqueue_issue(redis, {
        "channel": inbound.channel, "user_id": inbound.user_id,
        "text": inbound.text, "conversation_id": inbound.conversation_id,
    }, job_id="feishu:" + message_id)
    logger.info("飞书任务已入队：job={} chars={}", job_id, len(inbound.text))
    try:
        async with asyncio.timeout(2):
            await FeishuChannel().send(inbound.conversation_id, "收到，任务已进入队列，我会在完成后回复。")
    except (TimeoutError, RuntimeError, OSError) as exc:
        logger.warning("飞书回执失败：job={} error={}", job_id, type(exc).__name__)
    return job_id
