"""scripts/ch04_devmate_context.py —— 第 4 章：验证 Skills / Memory 生效

运行（项目根目录）：uv run python -m scripts.ch04_devmate_context
"""
import asyncio

from agent.main import agent_session
from scripts._common import print_all


async def main():
    # 这个任务会命中 fastapi-endpoint 规范，且涉及金额 → 应触发 AGENTS.md 的 Decimal 铁律
    task = (
        "在 app/ 下新增一个订单接口：POST /orders/quote，"
        "接收一组商品（单价、数量），返回订单总价。"
        "请遵循团队的接口规范，并按团队约定处理金额。"
    )

    # FilesystemBackend 下必须带 thread_id（checkpointer 需要）
    async with agent_session(
            thread_id="ch04-demo", user_id="alice", channel="cli"
    ) as agent:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"thread_id": "ch04-demo"}},
        )

    print_all(result)


if __name__ == "__main__":
    asyncio.run(main())
