"""channels/feishu.py —— 飞书渠道适配器（lark-oapi，长连接接收）

依赖：uv add lark-oapi
- 收：用 lark.ws.Client（长连接）+ EventDispatcherHandler 监听 im.message.receive_v1；
- 发：用 lark.Client 调 im.v1.message.create 发回复。
官方 SDK 写法已核实（larksuite/oapi-sdk-python）。
"""
from __future__ import annotations

import json

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

    def __init__(self):
        s = get_settings()
        self._app_id = s.feishu_app_id
        self._app_secret = s.feishu_app_secret.get_secret_value()
        # 发消息用的 API 客户端
        self._client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .build()
        )

    async def send(self, conversation_id: str, text: str) -> None:
        """把回复发回飞书会话（conversation_id = chat_id）。"""
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(conversation_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))   # 文本消息内容是 JSON 字符串
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