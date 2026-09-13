"""scripts/ch02_try_devmate.py —— 第 2 章：第一次跑 DevMate（异步 ainvoke）

运行（项目根目录）：uv run python -m scripts.ch02_try_devmate
"""
import asyncio

from agent.main import agent_session
from scripts._common import print_all

# 多步任务：逼 DevMate 先用 write_todos 列计划，便于看到任务清单
MULTI_STEP_TASK = (
    "这是一个多步骤任务。开始执行前，你必须先调用 write_todos 创建任务清单，"
    "并在执行过程中持续更新 todo 状态；不要只在最终回复中用文字列清单。\n\n"
    "为订单服务实现一个折扣计算模块，放在 discount.py：\n"
    "1. calc_subtotal(items) 计算小计（items 形如 [{'price':10.0,'qty':2}, ...]）；\n"
    "2. apply_coupon(subtotal, coupon) 应用优惠券，支持'满减'和'打折'两种类型；\n"
    "3. calc_final_total(items, coupon, vip_level) 综合计算最终应付，VIP 等级越高额外折扣越多；\n"
    "每个函数都要类型注解、docstring，并处理边界情况（空列表、无效优惠券）。"
)

# 简单任务（对照用）：模型大概率不列计划，任务清单会为空
SIMPLE_TASK = (
    "为订单服务写一个计算订单总价的函数 calc_order_total(items)，"
    "items 形如 [{'price': 10.0, 'qty': 2}, ...]，返回所有条目 price*qty 之和。"
    "放在 pricing.py 里，带类型注解和 docstring。"
)


async def main():
    task = MULTI_STEP_TASK   # 想对照"简单任务不列计划"，改成 SIMPLE_TASK 即可

    async with agent_session(thread_id="ch02-try") as agent:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": task}]}
        )

    print_all(result)        # 统一用 _common 的打印工具


if __name__ == "__main__":
    asyncio.run(main())
