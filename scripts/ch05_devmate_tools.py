"""scripts/ch05_devmate_tools.py —— 第 5 章：验证自定义工具 + MCPManager 容错

运行（项目根目录）：uv run python -m scripts.ch05_devmate_tools

包含两段演示：
  demo_custom_tools()  —— DevMate 调用自定义 git 工具
  demo_mcp_fault_tolerance() —— MCPManager 在 server 连不上时容错（warning 跳过，不崩）
"""
import asyncio

from agent.main import agent_session
from scripts._common import print_all


async def demo_custom_tools():
    """① 自定义工具：让 DevMate 用 git 工具看改动、给 commit message（不真的提交）。"""
    print("\n========== ① 自定义工具演示（git） ==========")
    task = (
        "查看当前仓库有哪些未提交的改动，"
        "用一句中文概述这些改动，并给出一个合适的 git commit message（先不要真的提交）。"
    )
    async with agent_session(
            thread_id="ch05-tools", user_id="alice", channel="cli"
    ) as agent:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"thread_id": "ch05-tools"}},
        )
    print_all(result)


async def demo_mcp_fault_tolerance():
    """② MCPManager 容错：故意配一个连不上的 server，验证它只 warning 跳过、不崩。

    这是 4.3 容错设计的直接体现——外部 MCP server 不可用时，
    DevMate 仍能正常构建、正常用其余工具。
    """
    print("\n========== ② MCPManager 容错演示 ==========")
    from tools.mcp import MCPManager

    # 故意给一个不存在的 server（端口没人监听），模拟"server 没启动/挂了"
    mgr = MCPManager(
        {"unreachable_docs": {
                "transport": "http",
                "url": "http://localhost:9999/mcp"
            }
        })

    tools = await mgr.get_tools()   # 不会抛异常：容错地跳过失败的 server
    print(f"容错结果：取回 {len(tools)} 个 MCP 工具（连不上的已被跳过，程序未崩溃）")
    print("→ 观察上面的日志，应有一条 ⚠️ 'MCP server「unreachable_docs」接入失败，已跳过'")


async def main():
    await demo_custom_tools()
    await demo_mcp_fault_tolerance()


if __name__ == "__main__":
    asyncio.run(main())
