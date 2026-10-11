"""后台长任务、会话串行、幂等入队与投递重试测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from arq import Retry

from tasks import queue, worker


def worker_context():
    """构造可观察的 Redis 锁和缓存测试上下文。"""
    lock = SimpleNamespace(acquire=AsyncMock(return_value=True), release=AsyncMock())
    redis = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock(), lock=lambda *args, **kwargs: lock)
    ctx = {"redis": redis, "checkpointer": object(), "store": None, "job_id": "job"}
    payload = {"channel": "web", "user_id": "alice", "text": "task", "conversation_id": "chat"}
    return ctx, payload, lock


@pytest.mark.asyncio
async def test_worker_processes_long_task_and_releases_lock(monkeypatch) -> None:
    """同一会话串行执行，并留下任务结果供投递恢复。"""
    ctx, payload, lock = worker_context()
    run = AsyncMock(return_value="done")
    monkeypatch.setattr(worker, "handle_message", run)
    assert await worker.process_issue(ctx, payload) == {"reply": "done", "conversation_id": "chat"}
    lock.release.assert_awaited_once()
    ctx["redis"].set.assert_awaited_once()
    assert worker.WorkerSettings.job_timeout >= 1800


@pytest.mark.asyncio
async def test_busy_conversation_requeues_before_agent(monkeypatch) -> None:
    """锁被占用时延后任务，避免相同 checkpoint 并发写入。"""
    ctx, payload, lock = worker_context()
    lock.acquire.return_value = False
    run = AsyncMock()
    monkeypatch.setattr(worker, "handle_message", run)
    with pytest.raises(Retry):
        await worker.process_issue(ctx, payload)
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_feishu_delivery_retry_reuses_reply(monkeypatch) -> None:
    """发送失败后重试只投递缓存结果，不再执行 coder。"""
    from channels.feishu import FeishuChannel
    ctx, payload, lock = worker_context()
    payload["channel"] = "feishu"
    ctx["redis"].get.return_value = b"cached reply"
    run = AsyncMock()
    send = AsyncMock(side_effect=RuntimeError("temporary send failure"))
    monkeypatch.setattr(worker, "handle_message", run)
    monkeypatch.setattr(FeishuChannel, "send", send)
    with pytest.raises(Retry):
        await worker.process_issue(ctx, payload)
    run.assert_not_awaited()
    lock.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_failure_remains_failure_and_unlocks(monkeypatch) -> None:
    """后台异常不能被伪装成成功回复。"""
    ctx, payload, lock = worker_context()
    monkeypatch.setattr(worker, "handle_message", AsyncMock(side_effect=ValueError("broken task")))
    with pytest.raises(ValueError, match="broken task"):
        await worker.process_issue(ctx, payload)
    lock.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_event_has_stable_job_id() -> None:
    """Redis 已存在任务时仍返回一致的事件 ID。"""
    redis = SimpleNamespace(enqueue_job=AsyncMock(return_value=None))
    assert await queue.enqueue_issue(redis, {"channel": "feishu"}, "feishu:message") == "feishu:message"
    assert redis.enqueue_job.await_args.kwargs["_job_id"] == "feishu:message"
