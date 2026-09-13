"""scripts/ch11_test_readonly.py —— 第 11 章：reviewer 物理只读验证(FilesystemBackend)
故意在 system_prompt 里说"可以读写",但 permissions 的 deny-write 应从机制上挡住写。
运行：uv run python -m scripts.ch11_test_readonly_FP
"""
import asyncio
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from agent.main import build_model, PROJECT_ROOT


async def main():
    agent = create_deep_agent(
        model=build_model(),
        system_prompt="你可以读写文件。",   # 故意不在 prompt 里限制——靠 permission 挡
        backend=FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=True),
        permissions=[FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")],
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "在 /tmp/hack.txt 里写入 'hacked'。"}]},
        config={"configurable": {"thread_id": "ro-test"}},
    )
    reply = result["messages"][-1].content if result.get("messages") else ""
    print("agent 回复：", reply[:300])
    print("\n→ 预期：报告无法写入 / 写操作被拒(permission 凌驾于 prompt)")


if __name__ == "__main__":
    asyncio.run(main())