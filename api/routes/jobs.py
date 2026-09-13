"""api/routes/jobs.py —— 方案二：arq 异步提交（入队即返回）+ 查结果"""
from uuid import uuid4
from fastapi import APIRouter, Request
from fastapi import Request
from gateway.limiter import limiter

router = APIRouter(prefix="/jobs", tags=["jobs-arq"])


@router.post("")
@limiter.limit("10/minute")   
async def submit_async(req_body: dict, request: Request):
    """提交到 arq 队列，立即返回 job_id。"""
    from tasks.queue import enqueue_issue
    payload = {
        "channel": req_body.get("channel", "api"),
        "user_id": req_body.get("user_id", "anonymous"),
        "text": req_body["text"],
        "conversation_id": req_body.get("conversation_id", uuid4().hex),
    }
    job_id = await enqueue_issue(request.app.state.arq_redis, payload)
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}")
async def query_job(job_id: str, request: Request):
    from tasks.queue import get_job_result
    return await get_job_result(request.app.state.arq_redis, job_id)

