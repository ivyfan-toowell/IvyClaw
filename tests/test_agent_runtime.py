"""Agent 沙箱运行时生命周期测试。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent import main


@pytest.mark.asyncio
async def test_agent_session_returns_agent_and_cleans_sandbox(monkeypatch) -> None:
    """普通调用只获得 Agent，离开上下文后沙箱必须被清理。"""
    agent = object()
    sandbox = object()
    runtime = main.AgentRuntime(agent=agent, sandbox=sandbox, client=None)
    cleanup = AsyncMock()

    monkeypatch.setattr(main, "create_agent_runtime", AsyncMock(return_value=runtime))
    from sandbox import manager as sandbox_manager

    monkeypatch.setattr(sandbox_manager, "cleanup_sandbox", cleanup)

    async with main.agent_session() as yielded_agent:
        assert yielded_agent is agent

    cleanup.assert_awaited_once_with(sandbox)


@pytest.mark.asyncio
async def test_execution_scorer_uses_runtime_sandbox(monkeypatch) -> None:
    """代码修改、隐藏测试和 pytest 必须发生在同一个沙箱。"""
    from eval import exec_scorer

    invoked_agent = SimpleNamespace(ainvoke=AsyncMock(return_value={"messages": []}))
    sandbox = SimpleNamespace(
        upload_files=lambda files: [],
        execute=lambda command: SimpleNamespace(output="1 passed", exit_code=0),
        download_files=lambda paths: [],
    )
    runtime = main.AgentRuntime(agent=invoked_agent, sandbox=sandbox, client=None)

    @asynccontextmanager
    async def fake_runtime_session(**kwargs):
        yield runtime

    monkeypatch.setattr(exec_scorer, "agent_runtime_session", fake_runtime_session)

    result = await exec_scorer.score_by_execution(
        None,
        {
            "id": "exec-test",
            "issue": "修改代码",
            "test_file": "/home/agent/tests/test_hidden.py",
            "test_code": "def test_hidden(): assert True",
            "target_file": "",
        },
    )

    invoked_agent.ainvoke.assert_awaited_once()
    assert result["score"] == 1.0
