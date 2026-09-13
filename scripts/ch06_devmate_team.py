"""scripts/ch06_devmate_team.py —— 第 6 章：五子代理团队 + 沙箱端到端

运行（项目根目录，需先 uv sync --extra sandbox 并配好沙箱 provider 凭据）：
    uv run python -m scripts.ch06_devmate_team

演示：给一个 Issue，DevMate 团队 planner→researcher→coder→tester（沙箱跑 pytest）→reviewer 协作，
最后由 reviewer 给出结构化审查结论。
"""
import asyncio

from agent.dispatcher import run_issue
from scripts._common import print_all


ISSUE = """
        请重构当前 pricing 模块，新增“多种优惠规则组合计算”能力。
        
        要求：
        1. 保留现有 calc_discounted_total 的兼容性，不能破坏已有调用。
        2. 新增会员折扣规则：silver 95 折、gold 9 折、platinum 85 折。
        3. 新增满减规则：订单满 100 减 10，满 300 减 40。
        4. 优惠券规则、会员折扣、满减规则需要按合理顺序组合应用，并避免最终金额小于 0。
        5. 金额计算统一使用 Decimal，并保留两位小数。
        6. 需要根据当前 app/pricing.py 和 tests/ 现有结构决定如何拆分代码，必要时可以新增文件，但不要无意义重构。
        7. 为新增逻辑补充完整 pytest，至少覆盖：
           - 单独使用每种优惠；
           - 多种优惠组合；
           - 边界金额；
           - 非法会员等级；
           - 最终金额不得小于 0。
        8. 修改后运行相关测试，并进行最终 reviewer 审查。
        """

    # """
    # "订单服务需要一个促销金额计算函数 calc_discounted_total(items, coupon)：\n"
    # "- items 形如 [{'price': '10.00', 'qty': 2}, ...]；\n"
    # "- coupon 支持 {'type':'amount','value':'5.00'}（满减）和 {'type':'percent','value':'10'}（打折）；\n"
    # "- 放在 /home/daytona/app/pricing.py，金额用 Decimal，带类型注解和 docstring；\n"
    # "- 测试写到 /home/daytona/tests/test_pricing.py，覆盖正常/边界/无效优惠券；\n"
    # "- 用 `cd /home/daytona && python -m pytest -q` 在沙箱里跑通测试。\n"
    # "（注意：所有文件和命令都用 /home/daytona/ 开头的绝对路径。）"
    # """


async def main():
    # 沙箱工作目录（Daytona 默认 /home/daytona）——项目就 seed 在它下面
    SANDBOX_WORKDIR = "/home/daytona"

    # fetch_paths：跑完后从沙箱取回 app/pricing.py，验证 agent 真的改了文件
    result = await run_issue(
        ISSUE,
        user_id="alice",
        channel="cli",
        fetch_paths=[f"{SANDBOX_WORKDIR}/app/pricing.py"],
        thread_id="ch06-devmate-team",
        reuse_sandbox=True,
    )
    print_all(result)

    # ① 验证 agent 真在沙箱里写了文件（取回的产物里应有 calc_discounted_total）
    print("\n=== 取回的产物：app/pricing.py（沙箱里 agent 实际写的内容）===")
    artifacts = result.get("artifacts") or {}
    pricing = artifacts.get(f"{SANDBOX_WORKDIR}/app/pricing.py")
    if pricing:
        print(pricing.decode("utf-8", errors="replace"))
    else:
        print("（没取回到 pricing.py —— 说明 agent 可能没真正写文件，检查是否 seed 成功、沙箱是否可写）")

    # ② reviewer 的结构化审查结论（response_format=ReviewResult → ToolMessage 里是 JSON）
    print("\n=== 审查结论（reviewer 的结构化输出）===")
    found = False
    for msg in result.get("messages", []):
        content = getattr(msg, "content", "")
        if isinstance(content, str) and '"approved"' in content:
            print(content)
            found = True
            break
    if not found:
        print("（未找到结构化审查结论 —— 多半是流程没走到 reviewer，常见于 coder 阶段就卡住，"
              "回头检查 seed 是否成功、沙箱里 app/ 是否存在）")


if __name__ == "__main__":
    asyncio.run(main())