"""真实 LangGraph 验证：角色工具约束与结构化审查能同时生效。"""
from typing import Any

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.dispatcher import StageToolsMiddleware
from subagents.schemas import ReviewResult
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.tools import tool
from middleware.cost import CostMeterMiddleware


class ScriptedModel(BaseChatModel):
    """只返回预设消息的离线工具调用模型。"""
    responses: list[Any]
    bound_names: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "offline-scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        """记录图实际绑定的工具，不访问外部模型。"""
        self.bound_names = [tool.get("function", {}).get("name", tool.get("name", ""))
                            if isinstance(tool, dict) else tool.name for tool in tools]
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


@pytest.mark.asyncio
async def test_readonly_stage_graph_blocks_fabricated_write(monkeypatch) -> None:
    """即使模型猜测 write_file 名称，也不能执行被禁止的文件写入。"""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    model = ScriptedModel(responses=[AIMessage(content="", tool_calls=[{
        "id": "forbidden", "name": "write_file", "args": {"file_path": "/private.py", "content": "hacked"},
    }]), AIMessage(content="已遵守只读限制，未写入文件。")])
    graph = create_deep_agent(model=model, middleware=[StageToolsMiddleware(readonly=True)])
    result = await graph.ainvoke({"messages": [{"role": "user", "content": "inspect only"}]})
    blocked = next(message for message in result["messages"] if message.type == "tool")
    assert blocked.status == "error" and "当前阶段不允许" in blocked.content
    assert result.get("files", {}) == {}  # 禁止调用未进入文件工具，无法产生文件写入。
    assert result["messages"][-1].content == "已遵守只读限制，未写入文件。"
    assert "write_file" not in model.bound_names and "task" not in model.bound_names


@pytest.mark.asyncio
async def test_readonly_stage_graph_keeps_review_schema(monkeypatch) -> None:
    """只读工具过滤不破坏 ReviewResult 的结构化返回。"""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    model = ScriptedModel(responses=[AIMessage(content="", tool_calls=[{
        "id": "review", "name": "ReviewResult", "args": {"approved": True, "summary": "通过", "issues": [], "security_notes": []},
    }])])
    graph = create_deep_agent(model=model, response_format=ReviewResult,
                              middleware=[StageToolsMiddleware(readonly=True)])
    result = await graph.ainvoke({"messages": [{"role": "user", "content": "review"}]})
    assert result["structured_response"].approved is True


@pytest.mark.asyncio
async def test_tool_loop_is_bounded_and_usage_keeps_messages() -> None:
    """重复工具请求按预算结束；成本中间件仍保存完整工具调用与结果。"""
    @tool
    def probe() -> str:
        """返回测试结果。"""
        return "probe result"

    model = ScriptedModel(responses=[AIMessage(content="", tool_calls=[{
        "id": f"probe-{number}", "name": "probe", "args": {},
    }]) for number in range(2)])
    graph = create_agent(model=model, tools=[probe], middleware=[CostMeterMiddleware(),
                         ModelCallLimitMiddleware(run_limit=2, exit_behavior="end")])
    result = await graph.ainvoke({"messages": [{"role": "user", "content": "loop"}]})
    assert not model.responses
    assert sum(message.type == "tool" for message in result["messages"]) == 2
    assert "limit" in result["messages"][-1].content.lower()
