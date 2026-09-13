"""scripts/ch07_model_routing.py —— 第 7 章：多模型路由 + Harness Profile 验证

运行（项目根目录）：uv run python -m scripts.ch07_model_routing
"""
import asyncio

from profiles.init import register_all_profiles
from infra.llm_router import get_model, get_model_for_role, ROLE_TO_TIER
from infra.settings import get_settings


def demo_routing():
    """① 路由：按档位/角色取模型，打印它们实际指向的模型名。"""
    print("\n========== ① 多模型路由 ==========")
    tiers = get_settings().model_tiers
    print("档位映射：", tiers)
    print("角色→档位：", ROLE_TO_TIER)
    for role in ROLE_TO_TIER:
        model = get_model_for_role(role)
        # 不同 LangChain 模型对象，模型名字段可能不同，这里尽量取一个可读标识
        name = getattr(model, "model_name", None) or getattr(model, "model", "?")
        print(f"  {role:<11} → {ROLE_TO_TIER[role]:<9} → 模型对象已构造（{name}）")


def demo_profile_registered():
    """② Harness Profile：注册后给出确认（生效与否在跑 agent 时由 harness 自动应用）。"""
    print("\n========== ② Harness Profile 注册 ==========")
    register_all_profiles()
    from profiles.qwen_profile import QWEN_PROFILE_VERSION
    print(f"已注册 qwen Harness Profile（版本：{QWEN_PROFILE_VERSION}）")
    print("→ create_deep_agent 选中 openai 兼容模型时会自动应用该 profile，无需改调用点。")


async def demo_team_with_routing():
    """③ 团队 + 路由 + profile 端到端（需沙箱凭据；没有可跳过本段）。"""
    print("\n========== ③ 团队跑 Issue（各子代理用各自档位模型）==========")
    register_all_profiles()  # 确保 profile 在构建 agent 前已注册
    from agent.dispatcher import run_issue
    from scripts._common import print_all

    issue = "给 app/pricing.py 增加一个 apply_vip_discount(total, vip_level) 函数，金额用 Decimal，并写 pytest 在沙箱跑通。"
    result = await run_issue(issue, user_id="alice", channel="cli")
    print_all(result)


async def main():
    #demo_routing()
    #demo_profile_registered()
    # 没有沙箱凭据就先注释下一行，只看路由与 profile 注册
    await demo_team_with_routing()


if __name__ == "__main__":
    asyncio.run(main())