"""文件协议和面向模型的命令输出使用不同边界。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from middleware.audit import ToolAuditMiddleware


@pytest.mark.asyncio
@pytest.mark.parametrize("command_result", [False, True])
async def test_execute_output_is_bounded_without_losing_exit_tail(command_result: bool) -> None:
    """普通结果和 Command 更新都保留错误尾部，限制传入模型的长输出。"""
    content = "x" * 20000 + "EXIT_CODE=1"
    message = ToolMessage(content=content, tool_call_id="exec", name="execute")
    result = Command(update={"messages": [message], "other": "kept"}) if command_result else message
    request = SimpleNamespace(tool_call={"name": "execute", "id": "exec", "args": {}})
    returned = await ToolAuditMiddleware().awrap_tool_call(request, AsyncMock(return_value=result))
    if command_result:
        assert returned.update["other"] == "kept"
        returned = returned.update["messages"][0]
    assert len(returned.content) < 8100 and returned.content.endswith("EXIT_CODE=1")
    assert message.content == content


@pytest.mark.asyncio
async def test_file_results_remain_complete() -> None:
    """读文件结果不受命令输出边界影响，完整 JSON 不被截断。"""
    message = ToolMessage(content="x" * 12000, tool_call_id="read", name="read_file")
    request = SimpleNamespace(tool_call={"name": "read_file", "id": "read", "args": {}})
    returned = await ToolAuditMiddleware().awrap_tool_call(request, AsyncMock(return_value=message))
    assert returned is message and len(returned.content) == 12000
