"""第 11 章：五子代理完整流程 + Reviewer 独立只读沙箱验证

验证目标：
1. 触发 Planner → Researcher → Coder → Tester → Reviewer
2. 确认 Reviewer 阶段真的调用 create_readonly_sandbox()
3. 确认 Reviewer 使用的是独立容器
4. 确认 Reviewer 沙箱 execute 也无法写文件

运行：
uv run python -m scripts.ch11_test_reviewer_flow
"""

import asyncio
import agent.dispatcher as dispatcher

# 保存真正的 create_readonly_sandbox
_real_create_readonly = dispatcher.create_readonly_sandbox
reviewer_sandbox_called = False

async def checked_create_readonly(source_sandbox):
    """包装真正的只读沙箱创建函数，并顺便验证它。"""
    global reviewer_sandbox_called

    readonly = await _real_create_readonly(source_sandbox)
    reviewer_sandbox_called = True

    print("\n========== Reviewer 沙箱检查 ==========")

    print("普通开发沙箱：", source_sandbox.container_id)
    print("Reviewer 沙箱：", readonly.container_id)

    # ① 两个容器必须不是同一个
    assert (
        source_sandbox.container_id != readonly.container_id
    ), "❌ Reviewer 仍然使用普通开发沙箱"

    print("✅ Reviewer 使用独立 Docker 容器")

    # ② Reviewer 沙箱尝试通过 execute 写文件
    result = readonly.execute(
        'echo "hacked" > /home/agent/reviewer_hack.txt'
    )

    print("Reviewer 写入 exit_code：", result.exit_code)
    print("Reviewer 写入输出：", result.output)

    assert result.exit_code != 0, (
        "❌ Reviewer 沙箱仍然可以通过 execute 写文件"
    )

    print("✅ Reviewer 沙箱物理只读生效")

    return readonly


async def main():
    # 临时把 dispatcher 使用的函数替换成我们的检查版
    dispatcher.create_readonly_sandbox = checked_create_readonly

    issue = """
这是一个复杂代码任务。

请先制定实现计划，并调查当前仓库现有代码和相关实现，
然后完成以下修改：

1. 新增一个简单的 Python 工具函数 is_even(n: int) -> bool；
2. 为它编写 pytest 测试，至少覆盖偶数和奇数；
3. 实际运行测试；
4. 最后进行 Reviewer 审查。

这是复杂任务，并且需要先 research 当前项目结构后再实现。
"""

    try:
        result = await dispatcher.run_issue(
            issue=issue,
            user_id="ch11-test-user",
            channel="cli",
            thread_id="ch11-reviewer-flow-test",
        )

        print("\n========== DevMate 最终结果 ==========")

        messages = result.get("messages", [])
        if messages:
            print(messages[-1].content)

        print("\n========== 最终验证 ==========")

        assert reviewer_sandbox_called, (
            "❌ 没有调用 create_readonly_sandbox，"
            "Reviewer 没有进入专属只读沙箱"
        )

        print("✅ Reviewer 专属沙箱创建流程已被调用")
        print("✅ Reviewer 与开发沙箱不是同一个容器")
        print("✅ Reviewer execute 写文件被拒绝")
        print("\n🎉 Reviewer 场景 B 验证通过")

    finally:
        # 恢复原函数，避免影响其他测试
        dispatcher.create_readonly_sandbox = _real_create_readonly


if __name__ == "__main__":
    asyncio.run(main())

