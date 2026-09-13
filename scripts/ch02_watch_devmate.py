"""scripts/ch02_watch_devmate.py —— 第 2 章：看 DevMate 一步步干活（异步流式 astream）

运行（项目根目录）：uv run python -m scripts.ch02_watch_devmate
"""
import asyncio

from agent.main import agent_session

# 用多步任务，便于看到它先 write_todos 列计划、再 write_file 写文件
MULTI_STEP_TASK = (
    "为订单服务实现一个折扣计算模块，放在 discount.py：calc_subtotal、apply_coupon、"
    "calc_final_total 三个函数，带类型注解、docstring，并处理空列表与无效优惠券。"
)


async def main():
    async with agent_session(thread_id="ch02-watch") as agent:
        # stream_mode="updates"：只打印每一步"新产生"的更新，最适合观察 Agent 决策过程
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": MULTI_STEP_TASK}]},
            stream_mode="updates",
        ):
            for node_name, update in chunk.items():
                print(f"\n▶ 节点：{node_name}")
                msgs = update.get("messages") if isinstance(update, dict) else None
                if msgs:
                    msgs[-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())
