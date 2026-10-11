"""已登录用户的后台任务提交与结果查询。"""
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import AuthUser, JobResponse, JobSubmission, MessageRequest
from gateway.limiter import limiter
from gateway.users import require_user
from infra.settings import get_settings
from tasks.queue import enqueue_issue, get_job_result

router = APIRouter(prefix="/jobs", tags=["jobs-arq"])


@router.post("", response_model=JobSubmission)
@limiter.limit("10/minute")
async def submit_async(req_body: MessageRequest, request: Request,
                       user: AuthUser = Depends(require_user)) -> JobSubmission:
    """身份取自会话；入队前登记结果归属。"""
    job_id = uuid4().hex
    await request.app.state.arq_redis.set("job-owner:" + job_id, user.user_id,
                                         ex=get_settings().job_result_ttl_seconds)
    await enqueue_issue(request.app.state.arq_redis, {
        "channel": "web", "user_id": user.user_id, "text": req_body.text,
        "conversation_id": req_body.conversation_id,
    }, job_id=job_id)
    return JobSubmission(job_id=job_id)


@router.get("/{job_id}", response_model=JobResponse, response_model_exclude_none=True)
async def query_job(job_id: str, request: Request,
                    user: AuthUser = Depends(require_user)) -> JobResponse:
    """只允许任务所有者查询；不存在与越权都返回 404。"""
    owner = await request.app.state.arq_redis.get("job-owner:" + job_id)
    if isinstance(owner, bytes):
        owner = owner.decode()
    if owner != user.user_id:
        raise HTTPException(404, "任务不存在")
    return JobResponse.model_validate(await get_job_result(request.app.state.arq_redis, job_id))

