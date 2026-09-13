"""scripts/ch11_devmate_docker.py —— 第 11 章：DevMate 在加固容器里跑一个 Issue

需 IVC_SANDBOX_PROVIDER=docker（默认）、镜像已构建、Docker 在跑。
运行：uv run python -m scripts.ch11_devmate_docker
"""
import asyncio

from agent.main import build_sandbox_backend


async def main():
    # 构建一个用加固容器后端的 agent（这里直接组装，演示 backend 可插拔）
    from deepagents import create_deep_agent
    from agent.main import build_model, DEVMATE_SYSTEM_PROMPT
    from sandbox.docker_manager import destroy_sandbox

    backend, sandbox, client, workdir = await build_sandbox_backend("ch11-test")

    try:
        agent = create_deep_agent(
            model=build_model(),
            system_prompt=DEVMATE_SYSTEM_PROMPT + (
                f"\n你运行在隔离容器里，项目代码在 {workdir}/ 下。"
                f"所有文件操作和命令都用 {workdir}/ 开头的绝对路径。"
            ),
            backend=backend,
        )
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": (
                f"在 {workdir}/app/util.py 写一个 is_even(n) 函数判断偶数，带类型注解；"
                f"再在 {workdir}/tests/test_util.py 写 pytest 测试，"
                f"然后用 cd {workdir} && python -m pytest -q 跑通。"
            )}],
        })
        print(result["messages"][-1].content[:500])

    finally:
        if sandbox is not None:
            await destroy_sandbox(sandbox)


if __name__ == "__main__":
    asyncio.run(main())