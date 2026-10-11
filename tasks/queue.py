"""持久队列生产者；幂等 ID 和任务状态查询。"""
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus
from infra.logging import get_logger
from infra.settings import get_settings

logger = get_logger()


async def get_arq_redis() -> ArqRedis:
    """创建共享的 arq Redis 池。"""
    return await create_pool(RedisSettings.from_dsn(get_settings().redis_url))


async def enqueue_issue(redis: ArqRedis, payload: dict[str, Any], job_id: str | None = None) -> str:
    """原子入队，重复事件保持相同 ID，失败时不会预先标记已处理。"""
    job_id = job_id or uuid4().hex
    payload = {**payload, "enqueued_at": datetime.now(timezone.utc).isoformat()}
    job = await redis.enqueue_job("process_issue", payload, _job_id=job_id)
    logger.info("任务入队：job={} channel={} duplicate={}", job_id, payload.get("channel"), job is None)
    return job_id


async def get_job_result(redis: ArqRedis, job_id: str) -> dict[str, Any]:
    """返回状态；不向客户端泄露 worker 异常堆栈。"""
    job = Job(job_id=job_id, redis=redis)
    status = await job.status()
    out = {"job_id": job_id, "status": status.value}
    if status == JobStatus.complete:
        try:
            out["result"] = await job.result(timeout=1)
        except Exception:
            logger.exception("任务失败：job={}", job_id)
            out["error"] = "任务执行失败，请查看服务端日志"
    return out
