"""channels/feishu.py —— 飞书渠道适配器（lark-oapi，长连接接收）

依赖：uv add lark-oapi
- 收：用 lark.ws.Client（长连接）+ EventDispatcherHandler 监听 im.message.receive_v1；
- 发：用 lark.Client 调 im.v1.message.create 发回复。
官方 SDK 写法已核实（larksuite/oapi-sdk-python）。
"""
from __future__ import annotations

import json
import asyncio

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from channels.base import ChannelAdapter, InboundMessage
from infra.settings import get_settings
from infra.logging import get_logger

logger = get_logger()


class FeishuChannel(ChannelAdapter):
    name = "feishu"

    def __init__(self) -> None:
        """构造飞书发送客户端。"""
        s = get_settings()
        self._app_id = s.feishu_app_id
        self._app_secret = s.feishu_app_secret.get_secret_value()
        # 发消息用的 API 客户端
        self._client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .timeout(10)
            .build()
        )

    async def send(self, conversation_id: str, text: str) -> None:
        """把回复发回飞书会话（conversation_id = chat_id）。"""
        chunks: list[str] = []
        buffer = ""
        size = 0
        for character in text or "（无内容）":
            width = len(character.encode("utf-8"))
            if size + width > 12000:
                chunks.append(buffer)
                buffer, size = "", 0
            buffer += character
            size += width
        chunks.append(buffer)
        for chunk in chunks:
            await asyncio.to_thread(self._send_text, conversation_id, chunk)

    def _send_text(self, conversation_id: str, text: str) -> None:
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(conversation_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(body)
            .build()
        )
        resp = self._client.im.v1.message.create(req)
        if not resp.success():
            logger.warning("飞书发消息失败：code={} msg={}", resp.code, resp.msg)
            raise RuntimeError(f"飞书发送失败 code={resp.code}")
