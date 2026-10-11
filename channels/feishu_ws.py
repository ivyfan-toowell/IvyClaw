"""飞书长连接只负责解析、可靠入队和快速回执；执行交给 arq worker。"""
import asyncio
import concurrent.futures
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from channels.base import InboundMessage
from channels.feishu_events import enqueue_feishu, parse_feishu_message
from infra.logging import get_logger
from infra.settings import get_settings
from tasks.queue import get_arq_redis

logger = get_logger()


def extract_feishu_message(event: P2ImMessageReceiveV1) -> InboundMessage | None:
    """复用 Webhook 解析器，兼容长消息的 post 格式。"""
    body = event.event
    if not body or not body.message or not body.sender:
        return None
    message = body.message
    sender = body.sender
    return parse_feishu_message(
        {"content": message.content, "message_type": message.message_type,
         "chat_id": message.chat_id, "message_id": message.message_id},
        {"sender_id": {"open_id": sender.sender_id.open_id if sender.sender_id else None},
         "sender_type": sender.sender_type},
    )


async def run() -> None:
    """接收 SDK 事件；保留并观察所有入队 Future 的异常。"""
    settings = get_settings()
    redis = await get_arq_redis()
    loop = asyncio.get_running_loop()
    pending: set[concurrent.futures.Future[Any]] = set()

    def completed(future: concurrent.futures.Future[Any]) -> None:
        pending.discard(future)
        try:
            future.result()
        except BaseException:
            logger.exception("飞书消息入队失败，请检查 Redis 和接收日志")

    def on_message(event: P2ImMessageReceiveV1) -> None:
        inbound = extract_feishu_message(event)
        if inbound is None:
            return
        message_id = event.event.message.message_id
        logger.info("飞书收到消息：message={} user={} chars={}", message_id, inbound.user_id, len(inbound.text))
        future = asyncio.run_coroutine_threadsafe(enqueue_feishu(redis, inbound, message_id), loop)
        pending.add(future)
        future.add_done_callback(completed)

    handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(on_message).build()

    def start_sdk() -> None:
        # SDK start() 使用模块级 loop；显式在其专用线程创建，避免与 asyncio.run 共用。
        import lark_oapi.ws.client as ws_client
        sdk_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(sdk_loop)
        ws_client.loop = sdk_loop
        try:
            lark.ws.Client(settings.feishu_app_id, settings.feishu_app_secret.get_secret_value(),
                           event_handler=handler, log_level=lark.LogLevel.INFO).start()
        finally:
            sdk_loop.close()

    logger.info("飞书长连接启动：任务执行需要 arq worker")
    try:
        await asyncio.to_thread(start_sdk)
    finally:
        if pending:
            await asyncio.gather(*(asyncio.wrap_future(future) for future in list(pending)), return_exceptions=True)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
