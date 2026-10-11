"""只读核对测试会话中的消息类型、长度和投递时间，不输出任务正文或凭据。"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import ListMessageRequest, GetMessageRequest

from channels.feishu_events import parse_feishu_message
from infra.settings import get_settings
from channels.feishu_events import enqueue_feishu
from tasks.queue import get_arq_redis


def check(chat_id: str, start_time: str) -> dict[str, Any]:
    """查询已授权测试会话，保存实际飞书 API 返回的消息元数据。"""
    settings = get_settings()
    client = lark.Client.builder().app_id(settings.feishu_app_id).app_secret(
        settings.feishu_app_secret.get_secret_value()).timeout(10).build()
    request = ListMessageRequest.builder().container_id_type("chat").container_id(chat_id).start_time(
        start_time).sort_type("ByCreateTimeAsc").page_size(50).build()
    response = client.im.v1.message.list(request)
    report: dict[str, Any] = {"apiCode": response.code, "messages": []}
    if not response.success():
        report["apiMessage"] = response.msg
        return report
    for item in response.data.items or []:
        content = item.body.content if item.body else ""
        inbound = parse_feishu_message({"message_type": item.msg_type, "content": content, "chat_id": chat_id},
                                      {"sender_type": "user", "sender_id": {"open_id": "probe"}})
        report["messages"].append({"messageId": item.message_id, "messageType": item.msg_type,
            "senderType": item.sender.sender_type if item.sender else None, "createdAtMs": item.create_time,
            "isConfiguredApp": item.sender.id == settings.feishu_app_id if item.sender else False,
            "senderIdType": item.sender.id_type if item.sender else None,
            "textChars": len(inbound.text) if inbound else 0,
            "oldParserAccepts": bool(json.loads(content).get("text", "").strip()) if content else False})
    report["hasMore"] = response.data.has_more
    path = Path("logs/live_feishu_check.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def replay(chat_id: str, message_id: str) -> str:
    """重放已授权测试会话的一条真实用户消息；独立任务 ID 保留原任务结果。"""
    settings = get_settings()
    client = lark.Client.builder().app_id(settings.feishu_app_id).app_secret(
        settings.feishu_app_secret.get_secret_value()).timeout(10).build()
    request = GetMessageRequest.builder().message_id(message_id).build()
    response = await asyncio.to_thread(client.im.v1.message.get, request)
    if not response.success():
        raise RuntimeError(f"飞书读取测试消息失败：code={response.code}")
    item = response.data.items[0]
    if item.chat_id != chat_id or not item.sender or item.sender.sender_type != "user":
        raise ValueError("只能重放指定测试会话的用户消息")
    inbound = parse_feishu_message({"message_type": item.msg_type, "content": item.body.content, "chat_id": chat_id},
                                   {"sender_type": "user", "sender_id": {"open_id": item.sender.id}})
    if inbound is None:
        raise ValueError("测试消息无法解析")
    redis = await get_arq_redis()
    try:
        return await enqueue_feishu(redis, inbound, message_id + ":live-replay-v3")
    finally:
        await redis.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chat_id")
    parser.add_argument("--start-time", required=True, help="UTC Unix 秒")
    parser.add_argument("--replay-message-id", help="显式重放指定的真实测试消息，不能视为长连接收到了新事件")
    args = parser.parse_args()
    print(json.dumps(check(args.chat_id, args.start_time), ensure_ascii=False, indent=2))
    if args.replay_message_id:
        print("replayedJobId=" + asyncio.run(replay(args.chat_id, args.replay_message_id)))
