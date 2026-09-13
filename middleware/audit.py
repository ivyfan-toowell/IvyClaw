"""middleware/audit.py —— DevMate 的工具审计与调用限制中间件（异步）

功能：
1. 记录每次工具调用及耗时；
2. task 调用时记录具体子代理；
3. 限制各子代理的调用次数，避免重复委派；
4. 限制主 Agent 高频工具调用，避免 edit/execute 等无限循环导致 token 失控。
"""

import time
from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command

from infra.logging import get_logger
from obs.metrics import AGENT_TOOL_CALLS, AGENT_TOOL_DURATION

logger = get_logger()



class ToolAuditMiddleware(AgentMiddleware):
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], "Command | ToolMessage"],
    ) -> "Command | ToolMessage":
        tool_name = request.tool_call["name"]      # 第3章确认：tool_call 是 dict，用 ['name']
        start = time.perf_counter()
        status = "ok"
        try:
            return await handler(request)
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = time.perf_counter() - start
            AGENT_TOOL_CALLS.labels(tool_name, status).inc()        # 埋点
            AGENT_TOOL_DURATION.labels(tool_name).observe(elapsed)  # 埋点
            logger.info("🔧 工具 {} {}（{:.0f} ms）", tool_name, status, elapsed * 1000)



# # -------------------------------------------------
# # 子代理调用次数上限
# # -------------------------------------------------
# TASK_LIMITS = {
#     "planner": 1,
#     "researcher": 1,
#     "coder": 2,
#     "tester": 2,
#     "reviewer": 2,
# }
#
# # -------------------------------------------------
# # 主 Agent 自己调用工具的次数上限
# # -------------------------------------------------
# MAIN_TOOL_LIMITS = {
#     "edit_file": 3,
#     "write_file": 2,
#     "execute": 3,
#     "read_file": 5,
#     "ls": 3,
# }
#
#
# class ToolAuditMiddleware(AgentMiddleware):
#     """记录工具调用，并限制子代理和主 Agent 的重复工具调用。"""
#
#     def __init__(self):
#         # 每个子代理已经被调用多少次
#         self._task_counts: dict[str, int] = {}
#
#         # 主 Agent 各工具已经调用多少次
#         self._main_tool_counts: dict[str, int] = {}
#
#     async def awrap_tool_call(
#         self,
#         request: ToolCallRequest,
#         handler: Callable[[ToolCallRequest], "Command | ToolMessage"],
#     ) -> "Command | ToolMessage":
#
#         tool_name = request.tool_call["name"]
#         tool_args = request.tool_call.get("args", {})
#         tool_call_id = request.tool_call["id"]
#
#         # =================================================
#         # 1. task：限制子代理调用次数
#         # =================================================
#         if tool_name == "task":
#             subagent_type = tool_args.get("subagent_type")
#
#             if not subagent_type:
#                 logger.warning(
#                     "⚠️ task 未识别到 subagent_type | args={}",
#                     tool_args,
#                 )
#
#             else:
#                 current = self._task_counts.get(subagent_type, 0)
#
#                 # 未登记的子代理默认最多调用 1 次
#                 limit = TASK_LIMITS.get(subagent_type, 1)
#
#                 if current >= limit:
#                     logger.warning(
#                         "⛔ 阻止重复调用：{} 已调用 {}/{} 次",
#                         subagent_type,
#                         current,
#                         limit,
#                     )
#
#                     return ToolMessage(
#                         content=(
#                             f"子代理 {subagent_type} 已达到最大调用次数 "
#                             f"{limit} 次。不要再次调用该子代理，也不要绕过限制"
#                             "自行重复执行该角色的工作。请根据已有结果继续，"
#                             "必要时进入审查或报告尚未解决的问题。"
#                         ),
#                         tool_call_id=tool_call_id,
#                     )
#
#                 self._task_counts[subagent_type] = current + 1
#
#                 logger.info(
#                     "🔧 调用子代理：{}（第 {}/{} 次）",
#                     subagent_type,
#                     current + 1,
#                     limit,
#                 )
#
#         # =================================================
#         # 2. 非 task：限制主 Agent 高频工具
#         # =================================================
#         elif tool_name in MAIN_TOOL_LIMITS:
#             current = self._main_tool_counts.get(tool_name, 0)
#             limit = MAIN_TOOL_LIMITS[tool_name]
#
#             if current >= limit:
#                 logger.warning(
#                     "⛔ 阻止主 Agent 重复调用：{} 已调用 {}/{} 次",
#                     tool_name,
#                     current,
#                     limit,
#                 )
#
#                 return ToolMessage(
#                     content=(
#                         f"工具 {tool_name} 已达到本次任务最大调用次数 "
#                         f"{limit} 次。不要继续重复执行同类操作。"
#                         "请使用已有结果继续流程，必要时进入审查或"
#                         "向用户说明尚未解决的问题。"
#                     ),
#                     tool_call_id=tool_call_id,
#                 )
#
#             self._main_tool_counts[tool_name] = current + 1
#
#             logger.info(
#                 "🔧 调用工具：{}（第 {}/{} 次）",
#                 tool_name,
#                 current + 1,
#                 limit,
#             )
#
#         # =================================================
#         # 3. 其他没有限制的工具，只记录日志
#         # =================================================
#         else:
#             logger.info(
#                 "🔧 调用工具：{}",
#                 tool_name,
#             )
#
#         # =================================================
#         # 4. 真正执行工具
#         # =================================================
#         start = time.perf_counter()
#
#         result = await handler(request)
#
#         cost_ms = (time.perf_counter() - start) * 1000
#
#         # =================================================
#         # 5. 完成日志
#         # =================================================
#         if tool_name == "task":
#             subagent_type = tool_args.get("subagent_type", "unknown")
#
#             logger.info(
#                 "✅ 子代理完成：{}（{:.0f} ms）",
#                 subagent_type,
#                 cost_ms,
#             )
#
#         else:
#             logger.info(
#                 "✅ 工具完成：{}（{:.0f} ms）",
#                 tool_name,
#                 cost_ms,
#             )
#
#         return result