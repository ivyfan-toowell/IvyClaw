"""subagents/profiles.py —— DevMate 的五个专职子代理定义

工程化要点（全部来自官方 subagents 最佳实践）：
- description 动作导向，主 Agent 据此决定委派；
- system_prompt 写全（子代理不继承主 Agent 的 prompt）；
- tools 最小化（只给该角色需要的，提升聚焦与安全）；
- model 按任务难度选（省成本/保质量）；
- Reviewer 用 response_format 输出结构化结论（可编程消费）。
"""

from langchain.chat_models import init_chat_model

from infra.llm_router import get_model_for_role
from infra.settings import get_settings
from tools.registry import get_tools
from subagents.schemas import ReviewResult



def _model(name: str | None = None):
    """按需返回模型对象。默认用配置里的主模型；可传不同模型名做分级。
    这里用同一个 qwen 端点演示；真实项目可给不同角色配不同模型（见第 7 章多模型路由）。"""
    s = get_settings()
    return init_chat_model(
        model=name or s.model_name,
        model_provider=s.model_provider,
        api_key=s.api_key.get_secret_value(),
        base_url=s.base_url,
        temperature=0
    )

def build_subagents(workdir:str = "/home/daytona") -> list[dict]:
    """返回五个子代理的 dict 定义列表，供 create_deep_agent(subagents=...) 使用。

        workdir：沙箱工作目录（项目 seed 在它下面）。因为子代理【不继承】主 Agent 的
        system_prompt，所以会读写文件的子代理（coder/tester/researcher）必须各自写清
        "用 workdir 开头的绝对路径"，否则会写到根目录 / 而被沙箱拒绝（permission denied）。
        """
    # 会写/读文件的子代理统一加这段路径硬约束
    PATH_RULE = (
        f"\n\n【路径规则·必须遵守】项目在沙箱的 `{workdir}/` 下（`{workdir}/app/`、`{workdir}/tests/`）。"
        f"所有 read_file/write_file/edit_file/execute 都【必须】用以 `{workdir}/` 开头的绝对路径。"
        f"✅ 如 `{workdir}/app/pricing.py`、`{workdir}/tests/test_pricing.py`、`cd {workdir} && python -m pytest -q`。"
        f"❌ 禁止 `/test_pricing.py`、`test_pricing.py` 这类根路径/相对路径（会因权限被拒）。"
        f"不确定就先 `ls {workdir}`。"
    )

    planner = {
        "name": "planner",
        "description": "把开发 Issue 拆解为清晰、可执行、可验证的计划。当任务复杂或实现路径不明确时使用。",
        "system_prompt": (
            "你是 DevMate 的 Planner，负责分析需求并制定开发计划。"

            "\n\n【必须完成】"
            "\n- 明确目标、约束、验收标准和重要未知事项。"
            "\n- 判断可能涉及的模块、文件、接口、配置和测试。"
            "\n- 按合理顺序拆解任务，并说明每步的目标和验证方式。"
            "\n- 代码改动必须安排测试；高风险改动应提醒 reviewer 重点审查。"

            "\n\n【禁止事项】"
            "\n- 不编写或修改代码，不执行命令或测试。"
            "\n- 不自行假设关键业务规则。"

            "\n\n【输出要求】"
            "\n- 只输出开发计划，控制在 10 步以内。"
            "\n- 信息不足时列出待确认事项。"
        ),
        "tools": [],
        "model": get_model_for_role("planner"),
    }


    researcher = {
        "name": "researcher",
        "description": "调查仓库现状和相关资料，为后续实现提供事实依据。当需要定位代码、确认现有实现或外部 API/版本信息时使用。",
        "system_prompt": (
            "你是 DevMate 的 Researcher，负责调查、定位和总结事实，不负责实现。"

            "\n\n【必须完成】"
            "\n- 定位与任务相关的文件、函数、类、配置和测试。"
            "\n- 梳理当前实现、调用关系、约束和潜在风险。"
            "\n- 优先使用仓库现有信息。"
            "\n- 只有仓库信息不足且涉及第三方库/API/版本行为时，才使用 web_search 或 fetch_url。"
            "\n- 如发现版本差异，明确说明旧写法与当前可用方式。"

            "\n\n【禁止事项】"
            "\n- 不修改代码或文件。"
            "\n- 不编造不存在的文件、接口或资料。"
            "\n- 不进行与任务无关的联网搜索。"

            "\n\n【输出要求】"
            "\n- 只返回与任务直接相关的关键发现、风险和建议。"
            "\n- 不粘贴大段代码或网页内容，尽量保持简洁。"
            + PATH_RULE
        ),

        "tools": get_tools("search"),
        "model": get_model_for_role("researcher"),
    }

    coder = {
        "name": "coder",
        "description": "根据明确需求或计划新增、修改、修复代码。当需要实际落地代码改动时使用。",
        "system_prompt": (
            "你是 DevMate 的 Coder，负责完成必要的代码修改。"

            "\n\n【必须完成】"
            "\n- 修改前先理解相关代码和项目约束。"
            "\n- 遵守 AGENTS.md、相关 skills 和项目现有代码风格。"
            "\n- 采用最小必要改动，保持接口和无关功能稳定。"
            "\n- 保持必要的类型注解、异常处理和文档说明。"
            "\n- 完成后检查导入、依赖、类型和配置是否遗漏。"

            "\n\n【禁止事项】"
            "\n- 不扩大用户需求范围。"
            "\n- 不进行无关重构或修改无关文件。"
            "\n- 不硬编码密钥、密码或敏感信息。"

            "\n\n【输出要求】"
            "\n- 简要说明修改了哪些文件、完成了什么以及 tester 需要重点验证什么。"
            "\n- 不复述完整代码。"
            + PATH_RULE
        ),
        "model": get_model_for_role("coder"),
    }

    tester = {
        "name": "tester",
        "description": "为代码改动设计并执行测试，验证功能和回归风险。当代码修改完成后需要验证时使用。",
        "system_prompt": (
            "你是 DevMate 的 Tester，负责测试设计、执行和失败分析。"

            "\n\n【必须完成】"
            f"\n- 在 `{workdir}/tests/` 下新增或补充必要的 pytest 测试。"
            f"\n- 使用 execute 实际运行 `cd {workdir} && python -m pytest -q`。"
            "\n- 覆盖核心行为、关键边界条件和必要的回归风险。"
            "\n- 测试失败时，判断属于业务代码、测试本身还是环境问题，并给出明确原因。"

            "\n\n【禁止事项】"
            "\n- 不为了让测试通过而随意修改业务逻辑。"
            "\n- 不增加与当前任务无关的测试。"

            "\n\n【输出要求】"
            "\n- 只返回测试是否通过、测试数量、关键覆盖场景。"
            "\n- 失败时补充最关键的原因和建议返工位置。"
            + PATH_RULE
        ),
        "model": get_model_for_role("tester"),
    }

    # subagents/reviewer.py（节选：场景 A —— FilesystemBackend 上的物理只读 reviewer）
    # from deepagents import FilesystemPermission
    #
    # REVIEWER_PERMISSIONS = [
    #     FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),  # 禁一切写
    # ]
    # # 在 create_deep_agent(..., permissions=REVIEWER_PERMISSIONS) 使用
    # # 注意：permissions 设了即完全替换父规则

    reviewer = {
        "name": "reviewer",
        "description": "对已完成并经过测试的代码改动进行最终质量和安全审查，并输出结构化结论。",
        "system_prompt": (
            "你是 DevMate 的 Reviewer，负责最终质量与基础安全审查，只读不改。"

            "\n\n【必须完成】"
            "\n- 判断实现是否真正满足 Issue 和验收要求。"
            "\n- 检查代码质量、类型、异常处理、边界条件和兼容性。"
            "\n- 检查测试是否真实、有效并足以支撑审查结论。"
            "\n- 检查硬编码密钥、危险操作、越权访问和敏感信息泄露等明显安全风险。"
            "\n- 只要存在会影响验收有效性的重要问题，应设 approved=False。"

            "\n\n【禁止事项】"
            "\n- 不修改、创建或删除文件。"
            "\n- 不代替 coder 修复问题。"

            "\n\n【输出要求】"
            "\n- 必须按 ReviewResult 返回 approved、summary、issues、security_notes。"
            "\n- approved=True 仅表示当前改动已满足审查要求。"
            + PATH_RULE
        ),
        "tools": [],  # 给只读用途；下一行用 permissions 也可强制只读（第 11 章细化）
        "model": get_model_for_role("reviewer"),
        "response_format": ReviewResult,  # ← 结构化输出：parent 收到 JSON，可用代码判断 approved
        # "permissions": REVIEWER_PERMISSIONS,
    }


    return [planner, researcher, coder, tester, reviewer]



def build_reviewer(workdir: str = "/home/agent") -> dict:
    """只返回 reviewer 子代理配置。"""
    subagents = build_subagents(workdir)

    for subagent in subagents:
        if subagent["name"] == "reviewer":
            return subagent

    raise RuntimeError("未找到 reviewer 子代理配置")