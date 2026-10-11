"""飞书事件可靠入队；通用入口要求登录并复用 dispatcher。"""
import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.schemas import AuthUser, MessageRequest, MessageResponse
from channels.base import InboundMessage
from channels.feishu_events import parse_feishu_message
from channels.handler import handle_message
from gateway.users import require_user
from infra.logging import get_logger
from infra.settings import get_settings
from tasks.queue import enqueue_issue

logger = get_logger()
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/feishu")
async def feishu_webhook(request: Request) -> JSONResponse:
    """校验飞书 token 后持久入队，HTTP 回调不等待 Agent 或发送接口。"""
    body = await request.json()
    settings = get_settings()
    token = settings.feishu_verification_token
    if not token:
        raise HTTPException(503, "未配置飞书 Webhook verification token")
    supplied = body.get("token") or body.get("header", {}).get("token") or ""
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, token):
        raise HTTPException(403, "飞书 token 无效")
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge", "")})
    header = body.get("header", {})
    if header.get("event_type") == "im.message.receive_v1":
        event = body.get("event", {})
        message = event.get("message", {})
        inbound = parse_feishu_message(message, event.get("sender", {}))
        if inbound:
            message_id = message.get("message_id") or header.get("event_id")
            if not message_id:
                raise HTTPException(422, "消息缺少幂等标识")
            logger.info("飞书 Webhook 接收：message={} chars={}", message_id, len(inbound.text))
            await enqueue_issue(request.app.state.arq_redis, {
                "channel": "feishu", "user_id": inbound.user_id,
                "text": inbound.text, "conversation_id": inbound.conversation_id,
            }, job_id="feishu:" + message_id)
    return JSONResponse({"code": 0})


@router.post("/generic", response_model=MessageResponse)
async def generic_webhook(body: MessageRequest, request: Request,
                          user: AuthUser = Depends(require_user)) -> MessageResponse:
    """同步兼容入口；用户标识由服务端会话取得。"""
    inbound = InboundMessage(channel="web", user_id=user.user_id,
                             text=body.text, conversation_id=body.conversation_id)
    reply = await handle_message(inbound, request.app.state.checkpointer, request.app.state.store,
                                 redis=request.app.state.redis)
    return MessageResponse(reply=reply)
