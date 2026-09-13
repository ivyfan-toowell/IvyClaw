"""scripts/ch10_hitl_demo.py —— HITL 最小 demo（独立示例，演示机制）

一个"删库"危险工具，用 interrupt_on 让它执行前必须人工批准。
这是 HITL 机制的最小可跑闭环——和 DevMate 主流程无关，纯讲清 interrupt/resume 怎么用。
运行：uv run python -m scripts.ch10_hitl_demo
（需模型可用；用内存 checkpointer 即可，demo 不需要持久化）
"""
import asyncio

from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from deepagents import create_deep_agent

from agent.main import build_model


@tool
async def delete_database(db_name: str) -> str:
    """删除指定的数据库（危险操作，不可逆）。"""
    # 真实场景这里会真的删库；demo 里只返回一句话
    return f"数据库 {db_name} 已删除。"


async def main():
    checkpointer = InMemorySaver()        # HITL 必须有 checkpointer（demo 用内存版够了）
    agent = create_deep_agent(
        model=build_model(),
        system_prompt="你是运维助手，按用户要求操作。",
        tools=[delete_database],
        checkpointer=checkpointer,
        interrupt_on={"delete_database": True},   # ← 删库前暂停，等人批
    )
    config = {"configurable": {"thread_id": "hitl-demo-1"}}

    # ① 让它做危险动作 → 应中断、等审批（不会真执行）
    result = await agent.ainvoke(
        {
            "messages": [{
            "role": "user",
            "content": "请删除名为 prod 的数据库。"}]
        },
        config=config,
    )

    if "__interrupt__" in result:
        print("① 已暂停，等待人工审批：")
        for itr in result["__interrupt__"]:
            print("   待批准动作：", getattr(itr, "value", itr))

        # ② 人批准 → resume，从断点继续真正执行
        # 关键：resume 的值是 {"decisions": [...]}，每个决策用 {"type": "approve"}
        # （approve 不是 accept；decisions 是列表，和待批动作一一对应）
        print("\n（模拟人点了『批准』）")
        result2 = await agent.ainvoke(
            Command(resume={"decisions": [{"type": "approve"}]}),
            #Command(resume={"decisions": [{"type": "reject", "message": "不允许删库"}]}),
            config=config,
        )
        print("② 批准后执行结果：", result2["messages"][-1].content[:200])

        # 想看"拒绝"的效果：把上面换成
        #   Command(resume={"decisions": [{"type": "reject", "message": "不允许删库"}]})
        # 删库不会执行，agent 会收到拒绝反馈
    else:
        print("（没触发中断——确认 interrupt_on 配了、模型确实调用了 delete_database）")


if __name__ == "__main__":
    asyncio.run(main())