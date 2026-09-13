"""tasks/worker.py —— arq worker + 任务定义（方案二：生产级）

三进程里的"worker"：独立运行，从 Redis 取任务执行。
启动：uv run arq tasks.worker.WorkerSettings

设计：on_startup 建一次持久化资源（saver/store），整个 worker 进程复用——
和第 8 章 lifespan、第 9 章 feishu_ws 用同一个 open_persistence，三处一致。
"""
import sys
import asyncio
from arq.connections import RedisSettings

from channels.base import InboundMessage
from channels.handler import handle_message
from infra.persistence import open_persistence
from infra.settings import get_settings
from infra.logging import get_logger

import time
from datetime import datetime, timezone
from prometheus_client import start_http_server
from obs.metrics import AGENT_TASK_DURATION, AGENT_QUEUE_WAIT, AGENT_QUEUE_LENGTH
from arq import cron


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = get_logger()


async def process_issue(ctx: dict, payload: dict) -> dict:
    """arq 任务：处理一个 Issue。返回值会被 arq 存为任务结果（job.result() 可取）。"""

    # 排队等待：用入队时塞进 payload 的 enqueued_at（不依赖 arq 内部字段）
    enqueued_at = payload.get("enqueued_at")
    if enqueued_at:
        try:
            wait = (datetime.now(timezone.utc)
                    - datetime.fromisoformat(enqueued_at)).total_seconds()
            AGENT_QUEUE_WAIT.observe(max(0.0, wait))
        except Exception:  # noqa: BLE001 时间戳异常不影响主流程
            pass

    start = time.perf_counter()

    inbound = InboundMessage(
        channel=payload["channel"],
        user_id=payload["user_id"],
        text=payload["text"],
        conversation_id=payload["conversation_id"],
    )

    checkpointer = ctx["checkpointer"]   # on_startup 放进 ctx 的共享资源
    store = ctx["store"]
    logger.info("worker 处理任务：conv={}", inbound.conversation_id)

    try:
        reply = await handle_message(
            inbound,
            checkpointer,
            store,
            tenant_id=payload.get("tenant_id", "default"),
        )
        # 飞书等"推"型渠道：跑完主动发回；webhook/web"拉"型：靠 job 结果查询
        if inbound.channel == "feishu":
            from channels.feishu import FeishuChannel
            await FeishuChannel().send(inbound.conversation_id, reply)

        return {
            "reply": reply,
            "conversation_id": inbound.conversation_id
        }
    finally:
        # 端到端执行耗时（用户真正等的时间）
        AGENT_TASK_DURATION.observe(time.perf_counter() - start)


async def on_startup(ctx: dict):
    pool, checkpointer, store = await open_persistence()
    ctx["pg_pool"], ctx["checkpointer"], ctx["store"] = pool, checkpointer, store
    start_http_server(8002)
    logger.info("arq worker 启动：持久化资源就绪")


async def on_shutdown(ctx: dict):
    if ctx.get("pg_pool"):
        await ctx["pg_pool"].close()


async def update_queue_length(ctx: dict):
    """周期性把队列长度写进 Gauge。"""
    try:
        jobs = await ctx["redis"].queued_jobs()      # arq 取待处理任务
        AGENT_QUEUE_LENGTH.set(len(jobs))
    except Exception as e:  # noqa: BLE001
        logger.warning("采集队列长度失败：{}", e)


class WorkerSettings:
    """arq 通过这个类发现配置。跑：uv run arq tasks.worker.WorkerSettings"""
    functions = [process_issue]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)  # 用已有 Redis
    cron_jobs = [cron(update_queue_length, second=set(range(0, 60, 5)))]