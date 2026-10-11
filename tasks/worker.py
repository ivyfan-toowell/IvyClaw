"""arq worker：长任务超时、会话串行和飞书结果投递。"""
import asyncio
import sys
import time
from datetime import datetime, timezone
from typing import Any

from arq import Retry, cron
from arq.connections import RedisSettings
from prometheus_client import start_http_server

from channels.base import InboundMessage
from channels.handler import handle_message
from channels.session import thread_id_for
from infra.logging import get_logger
from infra.persistence import open_persistence
from infra.settings import get_settings
from obs.metrics import AGENT_TASK_DURATION, AGENT_QUEUE_WAIT, AGENT_QUEUE_LENGTH
from profiles.qwen_profile import register_all_profiles

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = get_logger()


async def process_issue(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    """执行消息并持久化最终回复，投递重试不再次执行 Agent。"""
    enqueued_at = payload.get("enqueued_at")
    if enqueued_at:
        try:
            wait = (datetime.now(timezone.utc) - datetime.fromisoformat(enqueued_at)).total_seconds()
            AGENT_QUEUE_WAIT.observe(max(0.0, wait))
        except (ValueError, TypeError):
            logger.warning("任务入队时间格式无效")
    inbound = InboundMessage(channel=payload["channel"], user_id=payload["user_id"],
                             text=payload["text"], conversation_id=payload["conversation_id"])
    tenant_id = payload.get("tenant_id", "default")
    job_id = ctx.get("job_id", thread_id_for(inbound, tenant_id))
    settings = get_settings()
    redis = ctx["redis"]
    lock = redis.lock("thread-lock:" + thread_id_for(inbound, tenant_id),
                      timeout=settings.task_timeout_seconds + 30, blocking_timeout=0)
    if not await lock.acquire():
        raise Retry(defer=5)
    start = time.perf_counter()
    logger.info("worker 开始：job={} chars={}", job_id, len(inbound.text))
    try:
        cached = await redis.get("job-reply:" + job_id)
        if cached is None:
            reply = await handle_message(inbound, ctx["checkpointer"], ctx["store"], tenant_id=tenant_id, redis=redis)
            await redis.set("job-reply:" + job_id, reply, ex=settings.job_result_ttl_seconds)
        else:
            reply = cached.decode() if isinstance(cached, bytes) else cached
        if inbound.channel == "feishu":
            from channels.feishu import FeishuChannel
            try:
                await FeishuChannel().send(inbound.conversation_id, reply)
            except (RuntimeError, OSError) as exc:
                logger.warning("飞书投递失败，保留结果重试：job={}", job_id)
                raise Retry(defer=15) from exc
        logger.info("worker 完成：job={}", job_id)
        return {"reply": reply, "conversation_id": inbound.conversation_id}
    except (Retry, asyncio.CancelledError):
        raise
    except Exception:
        # 后台任务边界：记录真实异常并继续抛出，arq 将任务标记失败。
        logger.exception("worker 执行失败：job={}", job_id)
        if inbound.channel == "feishu":
            from channels.feishu import FeishuChannel
            try:
                await FeishuChannel().send(inbound.conversation_id, "任务执行失败，已记录日志，请联系管理员查看任务 " + job_id)
            except (RuntimeError, OSError):
                logger.exception("飞书错误通知投递失败：job={}", job_id)
        raise
    finally:
        await lock.release()
        AGENT_TASK_DURATION.observe(time.perf_counter() - start)


async def on_startup(ctx: dict[str, Any]) -> None:
    """worker 注册模型 profiles 并打开共享持久化资源。"""
    register_all_profiles()
    pool, checkpointer, store = await open_persistence()
    ctx["pg_pool"], ctx["checkpointer"], ctx["store"] = pool, checkpointer, store
    start_http_server(8002)
    logger.info("arq worker 启动：timeout={}s max_jobs={}", get_settings().task_timeout_seconds, WorkerSettings.max_jobs)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """关闭 worker 持久化池。"""
    if ctx.get("pg_pool"):
        await ctx["pg_pool"].close()


async def update_queue_length(ctx: dict[str, Any]) -> None:
    """定期采集等待队列长度。"""
    jobs = await ctx["redis"].queued_jobs()
    AGENT_QUEUE_LENGTH.set(len(jobs))


class WorkerSettings:
    """配置并发不超过沙箱容量，明确长任务和结果保留时间。"""
    functions = [process_issue]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = get_settings().task_timeout_seconds
    max_jobs = min(get_settings().sandbox_pool_size, get_settings().worker_max_jobs)
    keep_result = get_settings().job_result_ttl_seconds
    max_tries = get_settings().task_timeout_seconds // 5 + 1
    log_results = False
    cron_jobs = [cron(update_queue_length, second=set(range(0, 60, 5)))]
