"""scripts/ch03_devmate_with_mw.py —— 第 3 章：带审计/成本/上下文中间件跑 DevMate

运行（项目根目录）：uv run python -m scripts.ch03_devmate_with_mw
"""
import asyncio

from agent.main import agent_session
from scripts._common import print_all


async def main():
    task = (
        "为订单服务实现一个折扣计算模块，放在 discount.py：calc_subtotal、apply_coupon、"
        "calc_final_total 三个函数，带类型注解、docstring，处理空列表与无效优惠券。"
    )

    async with agent_session(
            thread_id="ch03-middleware", user_id="alice", channel="cli"
    ) as agent:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": task}]}
        )

    print_all(result)

    # 顺带看成本中间件累加进状态的 token（CostState 的字段）
    print("\n=== 累计 token（来自 CostMeterMiddleware）===")
    print("input :", result.get("total_input_tokens"))
    print("output:", result.get("total_output_tokens"))


if __name__ == "__main__":
    asyncio.run(main())
