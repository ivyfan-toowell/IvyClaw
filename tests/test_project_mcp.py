"""真实 MCP 协议发现/调用、路径边界和账户绑定测试。"""
import json
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest
from langgraph.store.memory import InMemoryStore
from mcp.shared.memory import create_connected_server_and_client_session

from app.memory import MemoryService
from tools.project_mcp import build_project_mcp, project_mcp_session


def fixture_backend(tmp_path):
    """仅在临时测试夹具运行静态可信工具脚本，模拟沙箱协议。"""
    def execute(command, timeout=None):
        argv = shlex.split(command)
        argv[0] = sys.executable
        result = subprocess.run(argv, cwd=tmp_path, capture_output=True, timeout=timeout)
        return SimpleNamespace(output=(result.stdout + result.stderr).decode("utf8", errors="replace"),
                               exit_code=result.returncode, truncated=False)
    return SimpleNamespace(execute=execute)


@pytest.mark.asyncio
async def test_real_mcp_lists_eight_tools_and_reads_searches_syntax(tmp_path) -> None:
    """通过 ClientSession 完成 initialize/list_tools/call_tool。"""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "example.py").write_text("def hello():\n    return 'ivy'\n", encoding="utf8")
    server = build_project_mcp(fixture_backend(tmp_path), tmp_path.as_posix(), None)
    async with create_connected_server_and_client_session(server) as session:
        listed = await session.list_tools()
        assert len(listed.tools) == 8
        for tool in listed.tools:
            assert "user_id" not in tool.inputSchema.get("properties", {})
        read = await session.call_tool("read_project_file", {"path": "app/example.py"})
        assert not read.isError and "def hello" in read.structuredContent["output"]
        search = await session.call_tool("search_workspace", {"query": "hello"})
        matches = json.loads(search.structuredContent["output"])
        assert matches[0]["line"] == 1 and matches[0]["path"] == "app/example.py"
        syntax = await session.call_tool("check_python_syntax", {"path": "app/example.py"})
        assert syntax.structuredContent["exitCode"] == 0
        (tmp_path / "app" / "example.py").write_text("def broken(\n", encoding="utf8")
        syntax = await session.call_tool("check_python_syntax", {"path": "app/example.py"})
        assert syntax.structuredContent["exitCode"] != 0


@pytest.mark.asyncio
async def test_mcp_path_escape_hidden_files_and_injection_rejected(tmp_path) -> None:
    """用户可填参数不能跳到沙箱根外、读取凭据或注入 shell。"""
    root = tmp_path / "workspace"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("private outside", encoding="utf8")
    (root / ".env").write_text("SECRET=hidden", encoding="utf8")
    server = build_project_mcp(fixture_backend(root), root.as_posix(), None)
    async with create_connected_server_and_client_session(server) as session:
        for path in ["../outside.txt", (tmp_path / "outside.txt").as_posix(), ".env", "x'; echo attacked"]:
            result = await session.call_tool("read_project_file", {"path": path})
            assert result.structuredContent["exitCode"] != 0
            assert "private outside" not in result.structuredContent["output"]
            assert "SECRET=hidden" not in result.structuredContent["output"]
        oversized = await session.call_tool("read_project_file", {"path": "any", "max_chars": 999999})
        assert oversized.isError


@pytest.mark.asyncio
async def test_mcp_memory_tool_bound_to_user_and_evidence(tmp_path) -> None:
    """记忆工具不会允许模型切换账户；无原文证据的写入失败。"""
    store = InMemoryStore()
    alice, bob = MemoryService(store, "alice"), MemoryService(store, "bob")
    text = "我喜欢详细解释，我使用 Python。"
    server = build_project_mcp(fixture_backend(tmp_path), tmp_path.as_posix(), alice, text)
    async with create_connected_server_and_client_session(server) as session:
        saved = await session.call_tool("remember_user_fact", {"fact": {"key": "language", "value": "Python", "evidence": "我使用 Python"}})
        assert not saved.isError
        rejected = await session.call_tool("remember_user_fact", {"fact": {"key": "role", "value": "admin", "evidence": "我是管理员"}})
        assert rejected.isError
        updated = await session.call_tool("set_user_preference", {"patch": {"responseStyle": "detailed"}, "evidence": "我喜欢详细解释"})
        assert not updated.isError
        recalled = await session.call_tool("recall_user_memory", {"query": "Python"})
        assert recalled.structuredContent["semantic"][0]["value"] == "Python"
    assert (await alice.preferences()).response_style == "detailed"
    assert not (await bob.recall()).semantic


@pytest.mark.asyncio
async def test_langchain_mcp_adapter_invokes_live_session(tmp_path) -> None:
    """加载的 LangChain 工具实际发送 MCP call_tool，生命周期覆盖调用。"""
    (tmp_path / "hello.txt").write_text("Hello Ivy", encoding="utf8")
    async with project_mcp_session(fixture_backend(tmp_path), tmp_path.as_posix(), None) as tools:
        tool = next(tool for tool in tools if tool.name == "read_project_file")
        result = await tool.ainvoke({"path": "hello.txt"})
        assert "Hello Ivy" in str(result)


@pytest.mark.asyncio
async def test_run_tests_stays_in_tests_and_reports_failure(tmp_path) -> None:
    """测试工具只在指定 tests 目录执行，并保留失败退出码。"""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text("def test_ok():\n    assert True\n", encoding="utf8")
    server = build_project_mcp(fixture_backend(tmp_path), tmp_path.as_posix(), None)
    async with create_connected_server_and_client_session(server) as session:
        good = await session.call_tool("run_project_tests", {"path": "tests"})
        assert good.structuredContent["exitCode"] == 0
        assert "1 passed" in good.structuredContent["output"]
        bad_path = await session.call_tool("run_project_tests", {"path": "."})
        assert bad_path.structuredContent["exitCode"] != 0
        (tests / "test_example.py").write_text("def test_fails():\n    assert False\n", encoding="utf8")
        failure = await session.call_tool("run_project_tests", {"path": "tests"})
        assert failure.structuredContent["exitCode"] != 0
        assert "1 failed" in failure.structuredContent["output"]
