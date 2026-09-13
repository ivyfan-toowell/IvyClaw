"""agent/dispatcher.py —— DevMate 团队任务编排入口

设计原则：
- 主 Agent 负责判断任务复杂度、是否需要 research；
- dispatcher 根据判断结果决定是否强制进入 Planner / Researcher；
- 代码研发闭环固定为 Coder → Tester → Reviewer；
- 各阶段使用独立 thread，减少上下文累积；
- 所有阶段共享同一个 Daytona 沙箱；
- 不共享完整历史，只提取并传递各阶段的最终摘要，保证上下游交接。
"""
from __future__ import annotations
import json

from langchain_core.utils.uuid import uuid7
from agent.main import create_agent_runtime, build_model
from deepagents import create_deep_agent
from sandbox.docker_manager import create_readonly_sandbox, destroy_sandbox
from sandbox.manager import cleanup_sandbox
from subagents.profiles import build_reviewer
from infra.logging import get_logger

logger = get_logger()



def _last_message_text(result: dict) -> str:
    """从一次 agent.ainvoke() 的结果中提取最后一条消息文本。

    用途：
    不把整个阶段的 messages / tool calls 全部传给下一阶段，
    只保留最后的阶段结论，降低 token，同时保留任务交接信息。
    """
    messages = result.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    content = getattr(last_message, "content", "")

    if isinstance(content, str):
        return content.strip()

    # 某些模型 / LangChain 版本的 content 可能不是纯字符串。
    return str(content).strip()




async def run_issue(
    issue: str,
    user_id: str = "anonymous",
    channel: str = "cli",
    fetch_paths: list[str] | None = None,
    thread_id: str | None = None,
    reuse_sandbox: bool = False,
) -> dict:

    thread_id = thread_id or str(uuid7())

    runtime = await create_agent_runtime(
        thread_id,
        user_id=user_id,
        channel=channel,
    )
    agent, sandbox, client = runtime.agent, runtime.sandbox, runtime.client


    def stage_config(stage: str) -> dict:
        """每个阶段使用独立 thread，避免继承上一阶段完整消息历史。"""
        return {"configurable": {"thread_id": f"{thread_id}-{stage}",}}

    try:
        # ① ========= 任务分类：只判断，不调用任何子代理 =========
        logger.info("进入任务分类阶段")

        classify_result = await agent.ainvoke({
                "messages": [{
                    "role": "user",
                    "content": f"""
                                你现在只负责判断任务类型，不执行任务，也不要调用任何子代理或工具。
                                
                                原始任务：
                                {issue}
                                
                                请只输出 JSON：
                                
                                {{
                                  "complexity": "simple" 或 "complex",
                                  "need_research": true 或 false
                                }}
                                
                                判断原则：
                                - simple：目标明确、改动局部、步骤少，不需要先拆解方案；
                                - complex：涉及多个规则、多个模块、兼容性、架构调整、复杂测试或多阶段实现；
                                - need_research=true：需要额外定位现有实现、确认资料/API/版本/外部信息时；
                                - 不要输出 JSON 以外的任何内容。
                                """,
                            }]
            },
            config=stage_config("classify"),
        )

        classify_text = _last_message_text(classify_result)

        complexity = "simple"
        need_research = False

        try:
            decision = json.loads(classify_text)
            complexity = decision.get("complexity", "simple")
            need_research = bool(decision.get("need_research", False))
        except Exception:
            logger.warning("⚠️任务分类结果解析失败，按 simple / no-research 继续：{}", classify_text)

        logger.info("任务分类结果：complexity={}, need_research={}", complexity, need_research)



        # 后续阶段的交接摘要
        planner_summary = ""
        research_summary = ""
        coder_summary = ""
        tester_summary = ""


        # ② ============== Planner：复杂任务必须调用 ==============

        if complexity == "complex":
            logger.info("进入 Planner 阶段")

            planner_result = await agent.ainvoke({
                    "messages": [{
                        "role": "user",
                        "content": f"""
                                    当前只执行【Planner 阶段】。
                                    
                                    原始任务：
                                    {issue}
                                    
                                    要求：
                                    - 必须调用 planner 子代理；
                                    - planner 负责拆解需求、明确实现步骤、约束和验收标准；
                                    - 不调用 coder、tester、reviewer；
                                    - 如需 research，只指出需要确认的问题，不在本阶段自行研究；
                                    - 最终请简洁总结可直接交给后续角色执行的规划；
                                    - planner 完成后立即结束本阶段。
                                    """,
                        }
                    ]
                },
                config=stage_config("planner"),
            )

            planner_summary = _last_message_text(planner_result)

            logger.info("Planner 阶段完成，已提取交接摘要（{} 字符）",len(planner_summary))



        # =============== Researcher：需要时必须调用 ===============

        if need_research:
            logger.info("进入 Researcher 阶段")

            researcher_result = await agent.ainvoke({
                    "messages": [{
                        "role": "user",
                        "content": f"""
                                    当前只执行【Researcher 阶段】。
                                    
                                    原始任务：
                                    {issue}
                                    
                                    Planner 规划（如有）：
                                    {planner_summary or "无"}
                                    
                                    要求：
                                    - 必须调用 researcher 子代理；
                                    - 负责定位现有代码、确认资料/API/版本或必要背景信息；
                                    - 只研究与当前任务直接相关的内容；
                                    - 不调用 coder、tester、reviewer；
                                    - 最终请简洁总结可直接交给 coder 使用的研究结论；
                                    - researcher 完成后立即结束本阶段。
                                    """,
                        }]
                },
                config=stage_config("researcher"),
            )

            research_summary = _last_message_text(researcher_result)

            logger.info("Researcher 阶段完成，已提取交接摘要（{} 字符）", len(research_summary))


        # ============ ④ Coder：接收 Planner / Researcher 的摘要 ============

        logger.info("进入 Coder 阶段")

        coder_result = await agent.ainvoke({
                "messages": [{
                        "role": "user",
                        "content": f"""
                                    当前只执行【Coder 阶段】。
                                    
                                    原始任务：
                                    {issue}
                                    
                                    Planner 规划：
                                    {planner_summary or "本任务未使用 Planner。"}
                                    
                                    Researcher 结论：
                                    {research_summary or "本任务未使用 Researcher。"}
                                    
                                    要求：
                                    - 必须调用 coder 子代理完成实际代码修改；
                                    - 结合上述规划、研究结论以及当前共享沙箱中的真实代码完成实现；
                                    - 如规划或研究结论与实际代码冲突，以当前真实代码和任务要求为准；
                                    - 不调用 tester、reviewer；
                                    - 最终简洁总结实际修改了什么，供 tester 接手；
                                    - coder 完成后立即结束本阶段；
                                    - 不重复调用 coder，除非本次明确失败。
                                    """,
                    }
                ]
            },
            config=stage_config("coder"),
        )

        coder_summary = _last_message_text(coder_result)

        logger.info("Coder 阶段完成，已提取交接摘要（{} 字符）", len(coder_summary))


        # ============= ⑤ Tester：主要看共享沙箱，同时接收 Coder 摘要 =============

        logger.info("进入 Tester 阶段")

        tester_result = await agent.ainvoke({
                "messages": [{
                        "role": "user",
                        "content": f"""
                                    当前只执行【Tester 阶段】。
                                    
                                    原始任务：
                                    {issue}
                                    
                                    Coder 交接摘要：
                                    {coder_summary or "无"}
                                    
                                    Coder 阶段已经结束，当前共享沙箱中包含最新代码。
                                    请以沙箱中的真实文件为准，不要只相信 Coder 的文字说明。
                                    
                                    要求：
                                    - 必须调用 tester 子代理；
                                    - 运行与本次修改相关的必要测试；
                                    - 检查实现是否满足原始任务和必要边界条件；
                                    - 不调用 coder、reviewer；
                                    - 最终明确说明测试是否通过、执行了哪些测试、是否存在失败项；
                                    - 测试结束后立即结束本阶段。
                                    """,
                    }]
            },
            config=stage_config("tester"),
        )

        tester_summary = _last_message_text(tester_result)

        logger.info("Tester 阶段完成，已提取交接摘要（{} 字符）", len(tester_summary))



        # ============== ⑥ Reviewer：使用专属只读沙箱 ==============


        logger.info("进入 Reviewer 阶段")
        readonly_sandbox = None
        try:
            # ① 根据当前开发沙箱创建只读副本
            readonly_sandbox = await create_readonly_sandbox(sandbox)
            # ② Reviewer 专属配置
            reviewer = build_reviewer(readonly_sandbox.workdir)
            # ③ 创建一个只绑定只读沙箱的 Reviewer Agent
            reviewer_agent = create_deep_agent(
                model=reviewer["model"],
                system_prompt=reviewer["system_prompt"],
                backend=readonly_sandbox,
                response_format=reviewer["response_format"],
            )
            # ④ 在只读沙箱里调用 reviewer
            reviewer_result = await reviewer_agent.ainvoke({
                    "messages": [{
                        "role": "user",
                        "content": f"""
                            当前只执行【Reviewer 阶段】。

                            原始任务：
                            {issue}

                            Planner 规划：
                            {planner_summary or "本任务未使用 Planner。"}

                            Researcher 结论：
                            {research_summary or "本任务未使用 Researcher。"}

                            Coder 交接摘要：
                            {coder_summary or "无"}

                            Tester 验证结果：
                            {tester_summary or "无"}

                            请基于当前只读沙箱中的真实代码和实际测试状态进行最终审查。
                            以上摘要只用于帮助理解上下文；如摘要与沙箱真实状态冲突，以沙箱为准。

                            要求：
                            - 审查功能正确性、测试覆盖、代码质量和安全性；
                            - 输出 approved 状态；
                            - approved=False 时明确列出 issues；
                        """,
                    }]},
                config=stage_config("reviewer"),
            )
            result = reviewer_result

        finally:
            # ⑤ Reviewer 用完立刻销毁自己的只读沙箱
            if readonly_sandbox is not None:
                await cleanup_sandbox(readonly_sandbox)



        # ================ ⑦ 下载产物 ================

        if fetch_paths:
            from langchain_daytona import DaytonaSandbox
            from sandbox.manager import download_artifacts

            artifacts = download_artifacts(
                DaytonaSandbox(sandbox=sandbox),
                fetch_paths,
            )
            result["artifacts"] = artifacts

        logger.info("Issue 处理完成：thread_id={}", thread_id)

        return result



    finally:
        if reuse_sandbox:
            logger.info("保留沙箱供后续复用：thread_id={}", thread_id)
        else:
            await cleanup_sandbox(sandbox)
            logger.info("沙箱已回收：thread_id={}", thread_id)
