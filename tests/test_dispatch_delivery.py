"""统一调度、飞书长消息和沙箱初始化的回归测试。"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent import dispatcher
from channels import handler
from channels.base import InboundMessage
from channels.feishu_events import parse_feishu_message
from channels.session import thread_id_for
from subagents.schemas import ReviewResult, TaskDecision


@pytest.mark.asyncio
async def test_handler_uses_dispatcher_and_persistence(monkeypatch) -> None:
    """长任务进入 dispatcher 而非主 Agent 自行执行。"""
    msg = InboundMessage("feishu", "alice", "修复" * 10000, "chat")
    run = AsyncMock(return_value={"messages": [SimpleNamespace(content="完成")]})
    monkeypatch.setattr(handler, "run_issue", run)
    assert await handler.handle_message(msg, "checkpoint", None, "tenant") == "完成"
    kwargs = run.await_args.kwargs
    assert kwargs["checkpointer"] == "checkpoint"
    assert kwargs["thread_id"] == thread_id_for(msg, "tenant")
    assert kwargs["user_id"] == "alice"


@pytest.mark.asyncio
async def test_classifier_keeps_deliverables_at_end_of_long_request(monkeypatch) -> None:
    """长任务末尾的代码交付要求不能在分类截断时丢失。"""
    text = "开始说明" + "背景" * 12000 + "最终要求：新增 app/example.py 和 tests/test_example.py"
    classifier = SimpleNamespace(ainvoke=AsyncMock(return_value={"structured_response":
        TaskDecision(kind="development", complexity="complex", need_research=True)}))
    monkeypatch.setattr(dispatcher, "build_model", lambda: object())
    monkeypatch.setattr(dispatcher, "create_agent", lambda **kwargs: classifier)
    decision = await dispatcher.classify_task(text)
    sent = classifier.ainvoke.await_args.args[0]["messages"][0]["content"]
    assert sent.startswith("开始说明") and sent.endswith("tests/test_example.py")
    assert len(sent) < 17000 and decision.kind == "development"


def test_thread_identity_includes_user_and_unambiguous_components() -> None:
    """同群不同用户、租户和渠道不会共享私有上下文。"""
    one = InboundMessage("web", "alice", "hi", "shared")
    two = InboundMessage("web", "bob", "hi", "shared")
    assert thread_id_for(one) != thread_id_for(two)
    assert thread_id_for(one, "a") != thread_id_for(one, "b")
    assert thread_id_for(one) == thread_id_for(one)


@pytest.mark.parametrize("localized", [True, False])
def test_feishu_long_post_is_not_silently_discarded(localized: bool) -> None:
    """长消息以 post 到达时完整保留文本。"""
    text = "实现复杂任务" * 5000
    post = {"title": "需求", "content": [[{"tag": "text", "text": text}]]}
    content = {"zh_cn": post} if localized else post
    msg = parse_feishu_message({"message_type": "post", "content": json.dumps(content), "chat_id": "chat"},
                                {"sender_id": {"open_id": "alice"}})
    assert msg is not None and msg.text == "需求\n" + text


@pytest.mark.parametrize("content", ["not JSON", "null", "[]"])
def test_feishu_malformed_content_is_ignored(content: str) -> None:
    """坏消息不能使 SDK 接收回调崩溃。"""
    assert parse_feishu_message({"message_type": "text", "content": content}, {}) is None


@pytest.mark.asyncio
async def test_dispatcher_directly_runs_five_roles_and_cleanup(monkeypatch) -> None:
    """复杂开发任务的五角色有真实的独立调用，reviewer 使用只读副本。"""
    sandbox, readonly = object(), object()
    runtime = SimpleNamespace(agent=object(), sandbox=sandbox, backend=sandbox, client=None, workdir="/home/agent")
    monkeypatch.setattr(dispatcher, "classify_task", AsyncMock(return_value=TaskDecision(kind="development", complexity="complex", need_research=True)))
    monkeypatch.setattr(dispatcher, "create_agent_runtime", AsyncMock(return_value=runtime))
    profiles = [{"name": name, "model": name, "system_prompt": name} for name in ["planner", "researcher", "coder", "tester", "reviewer"]]
    monkeypatch.setattr(dispatcher, "build_subagents", lambda _: profiles)
    monkeypatch.setattr(dispatcher, "get_settings", lambda: SimpleNamespace(sandbox_provider="docker", sandbox_workdir="/home/agent", stage_model_call_limit=40))
    monkeypatch.setattr(dispatcher, "create_readonly_sandbox", AsyncMock(return_value=readonly))
    cleanup = AsyncMock()
    monkeypatch.setattr(dispatcher, "cleanup_sandbox", cleanup)
    called = []
    configs = []

    def build(**kwargs):
        role = kwargs["model"]
        assert kwargs["backend"] is (readonly if role == "reviewer" else sandbox)

        async def invoke(data, config):
            called.append(role)
            configs.append(config)
            return {"messages": [SimpleNamespace(content=role + " done")],
                    "structured_response": ReviewResult(approved=True, summary="通过")}
        return SimpleNamespace(ainvoke=invoke)

    monkeypatch.setattr(dispatcher, "create_deep_agent", build)
    result = await dispatcher.run_issue("修改复杂任务", checkpointer="cp", store="store", thread_id="thread")
    assert called == ["planner", "researcher", "coder", "tester", "reviewer"]
    assert result["approved"] is True
    assert len({config["configurable"]["thread_id"] for config in configs}) == 5
    assert [call.args[0] for call in cleanup.await_args_list] == [readonly, sandbox]


@pytest.mark.asyncio
async def test_chat_does_not_create_sandbox_or_coder(monkeypatch) -> None:
    """解释类任务只回答，不修改代码。"""
    monkeypatch.setattr(dispatcher, "classify_task", AsyncMock(return_value=TaskDecision(kind="chat")))
    monkeypatch.setattr(dispatcher, "build_model", lambda: object())
    chat = SimpleNamespace(ainvoke=AsyncMock(return_value={"messages": []}))
    monkeypatch.setattr(dispatcher, "create_agent", lambda **kwargs: chat)
    runtime = AsyncMock()
    monkeypatch.setattr(dispatcher, "create_agent_runtime", runtime)
    await dispatcher.run_issue("解释队列", thread_id="thread", checkpointer="cp")
    runtime.assert_not_awaited()
    assert chat.ainvoke.await_args.kwargs["config"]["configurable"]["thread_id"] == "thread"


@pytest.mark.asyncio
async def test_seed_uploads_all_directories_without_caches(tmp_path) -> None:
    """缩进回归：app、tests、skills 全部上传。"""
    from sandbox.docker_manager import seed_project
    for folder in ["app", "tests", "skills"]:
        directory = tmp_path / folder
        directory.mkdir()
        (directory / "example.py").write_text("hello", encoding="utf8")
        (directory / "__pycache__").mkdir()
        (directory / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
    (tmp_path / "AGENTS.md").write_text("rules", encoding="utf8")
    uploaded = []
    sandbox = SimpleNamespace(workdir="/home/agent", container_id="test",
                              upload_files=lambda files: uploaded.extend(files) or [])
    await seed_project(sandbox, root=tmp_path)
    assert {path for path, _ in uploaded} == {"/home/agent/AGENTS.md", *[f"/home/agent/{d}/example.py" for d in ["app", "tests", "skills"]]}


@pytest.mark.asyncio
async def test_feishu_send_is_nonblocking_and_splits_utf8(monkeypatch) -> None:
    """同步 SDK 转到线程，Unicode 长回复完整分片。"""
    from channels.feishu import FeishuChannel
    channel = object.__new__(FeishuChannel)
    calls = []
    channel._send_text = lambda chat, text: calls.append((chat, text))
    text = "中😀" * 10000
    await channel.send("chat", text)
    assert "".join(chunk for _, chunk in calls) == text
    assert all(len(chunk.encode()) <= 12000 for _, chunk in calls)


@pytest.mark.asyncio
async def test_dispatcher_review_repair_is_bounded(monkeypatch) -> None:
    """审查一直失败只允许一轮返工，每轮仍必须经过 tester 和 reviewer。"""
    sandbox = object()
    runtime = SimpleNamespace(sandbox=sandbox, backend=sandbox, workdir="/home/agent")
    monkeypatch.setattr(dispatcher, "classify_task", AsyncMock(return_value=TaskDecision(kind="development")))
    monkeypatch.setattr(dispatcher, "create_agent_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(dispatcher, "build_subagents", lambda _: [
        {"name": role, "model": role, "system_prompt": role} for role in ["coder", "tester", "reviewer"]
    ])
    monkeypatch.setattr(dispatcher, "get_settings", lambda: SimpleNamespace(sandbox_provider="daytona", sandbox_workdir="/home/agent", stage_model_call_limit=40))
    cleanup = AsyncMock()
    monkeypatch.setattr(dispatcher, "cleanup_sandbox", cleanup)
    called = []

    def build(**kwargs):
        async def invoke(data, config):
            called.append(kwargs["model"])
            return {"messages": [{"content": "failed"}],
                    "structured_response": ReviewResult(approved=False, summary="仍有问题", issues=["测试失败"])}
        return SimpleNamespace(ainvoke=invoke)

    monkeypatch.setattr(dispatcher, "create_deep_agent", build)
    result = await dispatcher.run_issue("修复问题")
    assert called == ["coder", "tester", "reviewer", "coder", "tester", "reviewer"]
    assert result["approved"] is False
    cleanup.assert_awaited_once_with(sandbox)
