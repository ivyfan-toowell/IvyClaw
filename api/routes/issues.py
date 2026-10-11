"""已认证 Issue 入口；所有请求复用统一 dispatcher。"""
from uuid import uuid4
from fastapi import APIRouter, Depends, Request

from api.schemas import AuthUser, IssueRequest, IssueResponse
from channels.base import InboundMessage
from channels.handler import handle_message
from gateway.auth import require_api_key
from gateway.users import require_user

router = APIRouter(prefix="/issues", tags=["issues"])


@router.post("", response_model=IssueResponse)
async def submit_issue(req: IssueRequest, request: Request,
                       user: AuthUser = Depends(require_user)) -> IssueResponse:
    """按登录用户隔离会话，忽略客户端声明的身份。"""
    thread_id = req.thread_id or uuid4().hex
    inbound = InboundMessage(channel="api", user_id=user.user_id, text=req.issue, conversation_id=thread_id)
    reply = await handle_message(inbound, request.app.state.checkpointer, request.app.state.store,
                                 redis=request.app.state.redis)
    return IssueResponse(thread_id=thread_id, reply=reply)


@router.post("/secure")
async def submit_issue_secure(req: IssueRequest, request: Request,
                              tenant_id: str = Depends(require_api_key)) -> dict[str, str]:
    """保留 API Key 集成入口，按租户隔离渠道身份。"""
    inbound = InboundMessage(channel="integration_" + req.channel, user_id=req.user_id, text=req.issue,
                             conversation_id=req.thread_id or req.user_id)
    reply = await handle_message(inbound, request.app.state.checkpointer, request.app.state.store,
                                 tenant_id=tenant_id, redis=request.app.state.redis)
    return {"reply": reply, "tenant": tenant_id}



