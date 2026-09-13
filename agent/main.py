"""agent/main.py —— DevMate 主 Agent（第 4 章：接入 FilesystemBackend + Skills + Memory）

⚠️ 安全：本章用 FilesystemBackend 仅适用于本地开发/教学。
   生产/Web 服务请改用 StateBackend + 沙箱（第 8、11 章）。
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from langchain.agents.middleware import TodoListMiddleware
from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from subagents.profiles import build_subagents

from infra.settings import get_settings
from infra.logging import get_logger
from middleware.audit import ToolAuditMiddleware
from middleware.cost import CostMeterMiddleware
from middleware.context import RequestContextMiddleware
from infra.fallback import build_fallback_middleware
from middleware.concurrency import LLMConcurrencyMiddleware

from tools.registry import get_tools
from tools.mcp import MCPManager

logger = get_logger()

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ivyclaw/

DEVMATE_SYSTEM_PROMPT = """
你是团队协调者，优先通过 planner、researcher、coder、tester、reviewer 完成专业工作。

【调度规则】
优先将专业工作委派给对应子代理；子代理结果足以继续时，不得重复执行同类工作。
只有出现明确失败、矛盾或缺失信息时才允许返工；达到既定上限后，主 Agent 不得绕过限制自行接管同类修改或测试，应停止返工，并进入审查或报告未解决问题。

代码修改交给 coder，测试验证交给 tester，完成后交给 reviewer。
无论测试成功、测试失败、达到返工上限，还是存在未解决问题，都必须经过 reviewer。
如果任务仍有问题，reviewer 应返回 approved=False 并列出 issues；主 Agent 随后根据审查结果向用户报告

【任务编排原则】

1. 先理解任务目标、约束和验收标准，再决定需要调用哪些子代理。
   执行任务前，应先了解并遵守项目中的 AGENTS.md 和与当前任务相关的 skills。
   AGENTS.md 作为项目级约束，skills 作为具体任务的能力与操作指引。
   只读取与当前任务相关的 skill，避免加载无关内容。

2. 根据任务需要选择角色：
    - planner：拆解用户需求并列出执行计划；
    - researcher：负责完成定位代码、了解现状或确认资料/API/版本的任务；
    - coder：负责编写、修改或修复代码的任务；
    - tester：代码改动后，tester 进行测试和验证；
    - reviewer：每个测试完成后必须交给 reviewer 做最终质量与安全审查。

3. 同一个子代理默认调用一次。
   只有当前一次执行明确失败、测试不通过或审查要求返工时，才允许再次调用。

4. 所有代码修改、文件操作和命令执行必须遵守当前沙箱和路径规则。
   主 Agent 不应绕过子代理无必要地反复读取文件、修改代码或执行命令。

5. 如果遇到无法解决的环境、权限、依赖或信息缺失问题，应停止无效重试，并向用户说明真实原因。

6. 最终回复应简洁说明：
    - 实际完成了什么；
    - 关键产出或修改；
    - 验证结果；
    - 尚未解决的问题（如有）。
    
【代码任务固定流程】

对于涉及代码修改的任务：

coder → tester → reviewer

必须严格遵守以上顺序。

- coder 未完成前，不得调用 tester 或 reviewer。
- tester 未完成前，不得调用 reviewer。
- reviewer 是每轮研发闭环的最后一步，不得省略。
- tester 通过且 reviewer approved=True 后，立即结束任务。
- tester 失败：只允许 coder 修复一次，再 tester，再 reviewer。
- reviewer approved=False：只允许 coder 根据 issues 修复一次，再 tester，再 reviewer。
- 不得仅为“再次确认”重复调用 tester、reviewer 或 coder。

"""

def build_model():
        s = get_settings()

        return init_chat_model(
        model=s.model_name,
        model_provider=s.model_provider,
        api_key=s.api_key.get_secret_value(),
        base_url=s.base_url,
        temperature=0,
        max_retries=s.max_retries,
        timeout=s.timeout,
    )

@dataclass(slots=True)
class AgentRuntime:
    """保存 Agent 及其沙箱生命周期资源。"""

    agent: Any
    sandbox: Any
    client: Any | None


async def build_agent(
        sandbox_backend: Any,
        workdir: str,
        checkpointer=None,
        store=None,
        user_id: str = "anonymous",
        channel: str = "cli",
)-> Any:
    """使用已有沙箱后端组装并返回 DevMate Agent。

    - backend 用沙箱（自动提供文件工具 + execute），取代第 4 章的 FilesystemBackend；
    - 沙箱在新建时已被 seed 进 app/ tests/ skills/ AGENTS.md（见 sandbox/manager.py）；
    - skills/memory 指向沙箱工作目录下 seed 后的真实路径（workdir/skills 等）；
    - subagents 注入五个专职子代理；
    - 密钥（API key）只在主进程的 build_model() 里用，绝不传进沙箱。
    沙箱的创建与销毁由 create_agent_runtime/agent_session 负责。
    """

    if checkpointer is None:
        checkpointer = MemorySaver()

    mcp_tools = await MCPManager.from_settings().get_tools()

    agent = create_deep_agent(
        model=build_model(),
        system_prompt=DEVMATE_SYSTEM_PROMPT + (
            f"\n\n【执行环境与路径规则——必须严格遵守】"
            f"\n你运行在一个沙箱里，项目代码已位于 `{workdir}/` 下（含 `{workdir}/app/`、`{workdir}/tests/`）。"
            f"\n⚠️ 所有文件操作（write_file/edit_file/read_file）和命令（execute）都【必须】使用以 `{workdir}/` 开头的【绝对路径】。"
            f"\n✅ 正确：写测试到 `{workdir}/tests/test_pricing.py`、改代码 `{workdir}/app/pricing.py`、"
            f"跑测试 `cd {workdir} && python -m pytest -q`。"
            f"\n❌ 错误（会因权限被拒绝，绝不要这样）：`/test_pricing.py`、`test_pricing.py`、`/app/pricing.py` 这类根路径或相对路径。"
            f"\n如果你不确定某文件在哪，先用 `ls {workdir}` 查看，再用绝对路径操作。"
            "\n\n你是团队负责人：对复杂 Issue，先用 task() 委派给 planner 规划，"
            "再依次委派 researcher/coder/tester/reviewer。你只做协调，不亲自写大量代码。"
            "委派时，把上面的【绝对路径规则】一并转达给子代理。"
        ),
        backend=sandbox_backend,
        subagents=build_subagents(workdir),
        # 路径相对 backend 的 root（= PROJECT_ROOT），用正斜杠（官方要求）
        skills=[f"{workdir}/skills"],
        memory=[f"{workdir}/AGENTS.md"],
        middleware=[
            #TodoListMiddleware(),
            RequestContextMiddleware(user_id=user_id, channel=channel),
            ToolAuditMiddleware(),
            CostMeterMiddleware(),
            LLMConcurrencyMiddleware(),
            build_fallback_middleware(),
        ],
        # checkpointer=MemorySaver(),   # 备好；FilesystemBackend + 后续 HITL 需要它
        checkpointer=checkpointer,  # ← 外部传入（lifespan 的 AsyncPostgresSaver）
        store=store,
    )
    logger.info("DevMate 团队版构建完成：5 子代理 + 沙箱后端（项目已 seed 到 {}）", workdir)
    return agent


async def create_agent_runtime(
        thread_id: str | None = None,
        checkpointer: Any = None,
        store: Any = None,
        user_id: str = "anonymous",
        channel: str = "cli",
) -> AgentRuntime:
    """创建沙箱，并返回绑定该沙箱的 Agent 运行时。"""
    backend, sandbox, client, workdir = await build_sandbox_backend(thread_id)
    try:
        agent = await build_agent(
            backend,
            workdir,
            checkpointer=checkpointer,
            store=store,
            user_id=user_id,
            channel=channel,
        )
    except BaseException:
        from sandbox.manager import cleanup_sandbox

        await cleanup_sandbox(sandbox)
        raise
    return AgentRuntime(agent=agent, sandbox=sandbox, client=client)


@asynccontextmanager
async def agent_runtime_session(**kwargs: Any) -> AsyncIterator[AgentRuntime]:
    """提供 Agent 运行时，并在退出时自动清理其沙箱。"""
    runtime = await create_agent_runtime(**kwargs)
    try:
        yield runtime
    finally:
        from sandbox.manager import cleanup_sandbox

        await cleanup_sandbox(runtime.sandbox)


@asynccontextmanager
async def agent_session(**kwargs: Any) -> AsyncIterator[Any]:
    """仅向调用方提供 Agent，并在退出时自动清理沙箱。"""
    async with agent_runtime_session(**kwargs) as runtime:
        yield runtime.agent


# agent/main.py（新增：沙箱后端按配置可插拔）

async def build_sandbox_backend(thread_id: str | None = None):
    """
    按 IVC_SANDBOX_PROVIDER 选用沙箱后端，返回 (backend, workdir)。
    docker  → 自托管加固容器（本章，本地可跑）
    daytona → 外部托管沙箱（第 6 章）
    两者都是 BaseSandbox，create_deep_agent(backend=...) 一视同仁。
    """
    s = get_settings()

    if s.sandbox_provider == "docker":
        from sandbox.docker_manager import create_one_sandbox, seed_project
        sandbox = await create_one_sandbox()
        await seed_project(sandbox)
        return sandbox, sandbox, None, s.sandbox_workdir
    else:  # daytona —— 第 6 章那套
        from sandbox.manager import get_or_create_sandbox_backend
        backend, sandbox, client, workdir = get_or_create_sandbox_backend(thread_id or "default")
        return backend, sandbox, client, workdir
