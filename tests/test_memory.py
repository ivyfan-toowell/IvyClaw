"""记忆隔离、持久化、证据验证及有界上下文测试。"""
import json
from unittest.mock import AsyncMock

import pytest
from langgraph.store.memory import InMemoryStore

from app import memory as module
from app.memory import MemoryService
from app.schemas import MemoryExtraction, MemoryFact, PreferenceEvidence, PreferencePatch


@pytest.mark.asyncio
async def test_record_turn_restores_history_preferences_and_semantics() -> None:
    """重建服务对象后同一用户仍有历史与长期记忆。"""
    store = InMemoryStore()
    service = MemoryService(store, "alice")
    text = "我使用 Python 开发，偏好详细解释。"
    extraction = MemoryExtraction(
        facts=[MemoryFact(key="primary_language", value="Python", evidence="我使用 Python 开发")],
        preferences=[PreferenceEvidence(field="response_style", value="detailed", evidence="偏好详细解释")],
    )
    await service.record_turn("conversation", text, "任务完成", extraction)
    restored = MemoryService(store, "alice", channel="api")
    recall = await restored.recall("Python")
    assert recall.preferences.response_style == "detailed"
    assert recall.semantic[0].value == "Python"
    assert recall.episodic[0].reply == "任务完成"
    record = await restored.conversation("conversation")
    assert record is not None and record.turns[0].user_text == text
    context = json.loads(await restored.context("conversation", "继续工作"))
    assert context["preferences"]["responseStyle"] == "detailed"
    assert context["recentTurns"][0]["assistant"] == "任务完成"


@pytest.mark.asyncio
async def test_memory_isolation_user_tenant_channel() -> None:
    """猜测他人会话 ID 或事实 key 不能跨越记忆命名空间。"""
    store = InMemoryStore()
    alice = MemoryService(store, "alice")
    await alice.record_turn("shared", "我的项目是 Ivy", "收到", MemoryExtraction())
    await alice.remember_fact(MemoryFact(key="project", value="Ivy", evidence="项目是 Ivy"), "我的项目是 Ivy")
    for service in [MemoryService(store, "bob"), MemoryService(store, "alice", tenant_id="other"),
                    MemoryService(store, "alice", channel="feishu")]:
        assert await service.conversation("shared") is None
        assert not (await service.recall()).semantic
        assert not (await service.recall()).episodic


@pytest.mark.asyncio
async def test_extraction_failure_preserves_episode_and_chat(monkeypatch) -> None:
    """可选提取失败不会丢失完成的对话。"""
    monkeypatch.setattr(module, "extract_user_memory", AsyncMock(side_effect=TimeoutError("model timeout")))
    service = MemoryService(InMemoryStore(), "alice")
    await service.record_turn("conversation", "完成任务", "已完成")
    assert (await service.conversation("conversation")).turns[0].reply == "已完成"
    assert (await service.recall()).episodic[0].user_text == "完成任务"


@pytest.mark.asyncio
async def test_facts_need_evidence_and_do_not_store_credentials() -> None:
    """拒绝无证据的用户属性，以及密码/密钥记忆。"""
    service = MemoryService(InMemoryStore(), "alice")
    for fact, text in [
        (MemoryFact(key="role", value="管理员", evidence="我是管理员"), "你好"),
        (MemoryFact(key="api_key", value="secret123", evidence="我的 API key 是 secret123"), "我的 API key 是 secret123"),
    ]:
        with pytest.raises(ValueError):
            await service.remember_fact(fact, text)
    assert not (await service.recall()).semantic


@pytest.mark.asyncio
async def test_disable_extraction_keeps_history_and_existing_preferences(monkeypatch) -> None:
    """关闭长期事实提取仍保留对话，偏好按局部更新合并。"""
    service = MemoryService(InMemoryStore(), "alice")
    await service.update_preferences(PreferencePatch(preferred_language="en-US", response_style="detailed"))
    await service.update_preferences(PreferencePatch(remember_facts=False))
    extract = AsyncMock()
    monkeypatch.setattr(module, "extract_user_memory", extract)
    await service.record_turn("conversation", "hello", "hi")
    extract.assert_not_awaited()
    preferences = await service.preferences()
    assert preferences.preferred_language == "en-US" and preferences.response_style == "detailed"
    assert (await service.recall()).episodic


@pytest.mark.asyncio
async def test_recent_context_is_bounded_and_valid_json() -> None:
    """长会话只注入最近窗口，完整经历仍持久保存。"""
    service = MemoryService(InMemoryStore(), "alice")
    for index in range(12):
        await service.record_turn("conversation", f"{index}:" + "中" * 6000, "答" * 6000, MemoryExtraction())
    context = await service.context("conversation", "继续")
    data = json.loads(context)
    assert len(context) <= 24000
    assert len(data["recentTurns"]) <= 6
    assert len((await service.conversation("conversation")).turns) == 12
    assert len((await service.recall(limit=20)).episodic) == 12


@pytest.mark.asyncio
async def test_handler_injects_and_records_memory(monkeypatch) -> None:
    """渠道入口同时完成读取记忆、协作注入和对话结束写入。"""
    from channels import handler
    from channels.base import InboundMessage
    store = InMemoryStore()
    service = MemoryService(store, "alice")
    await service.update_preferences(PreferencePatch(response_style="detailed"))
    run = AsyncMock(return_value={"messages": [{"content": "完成"}]})
    monkeypatch.setattr(handler, "run_issue", run)
    monkeypatch.setattr(module, "extract_user_memory", AsyncMock(return_value=MemoryExtraction()))
    await handler.handle_message(InboundMessage("web", "alice", "task", "conversation"), None, store)
    assert "detailed" in run.await_args.kwargs["memory_context"]
    assert isinstance(run.await_args.kwargs["memory_service"], MemoryService)
    assert (await service.conversation("conversation")).turns[0].reply == "完成"
