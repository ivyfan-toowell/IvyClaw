"""api/routes/issues.py —— 提交 Issue 的业务路由"""
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from gateway.auth import require_api_key
from channels.base import InboundMessage
from channels.handler import handle_message

from agent.main import agent_session
from api.schemas import IssueRequest, IssueResponse
from api.deps import get_checkpointer, get_store

router = APIRouter(prefix="/issues", tags=["issues"])


@router.post("", response_model=IssueResponse)
async def submit_issue(
    req: IssueRequest,
    checkpointer=Depends(get_checkpointer),   # 注入 lifespan 建好的共享资源
    store=Depends(get_store),
) -> IssueResponse:
    # thread_id：客户端传了就用它（续聊/断点续跑），没传就新建
    thread_id = req.thread_id or uuid4().hex

    # 构建 agent（轻组装），传入共享的持久化资源
    async with agent_session(
            thread_id=thread_id,
            checkpointer=checkpointer,
            store=store,
            user_id=req.user_id,
            channel=req.channel,
    ) as agent:
        # 异步调用，带 thread_id —— 同一 thread_id 下次请求会带着历史上下文继续
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": req.issue}]},
            config={"configurable": {"thread_id": thread_id}},
        )

    reply = result["messages"][-1].content if result.get("messages") else ""
    return IssueResponse(thread_id=thread_id, reply=reply)



@router.post("/secure")
async def submit_issue_secure(
    req: IssueRequest,
    request: Request,
    tenant_id: str = Depends(require_api_key),   # ← 鉴权返回租户 id
):
    """需要 gateway-API-Key 的端点；租户身份贯穿到会话隔离。"""
    inbound = InboundMessage(
        channel=req.channel,
        user_id=req.user_id,
        text=req.issue,
        conversation_id=req.thread_id or req.user_id,
    )
    reply = await handle_message(
        inbound,
        request.app.state.checkpointer,
        request.app.state.store,
        tenant_id=tenant_id,                     # ← 一路传到 thread 派生，按租户隔离
    )
    return {"reply": reply, "tenant": tenant_id}





# # 通用模式：把同步阻塞调用包成不阻塞事件循环的协程
# import asyncio
#
# def some_blocking_sync_call(x):     # 假设这是个只有同步接口的库
#     ...
#
# async def use_it(x):
#     # ❌ 直接 await 不了（它不是协程）；直接调会阻塞事件循环
#     # ✅ 丢到线程池，事件循环不被卡住
#     result = await asyncio.to_thread(some_blocking_sync_call, x)
#     return result



