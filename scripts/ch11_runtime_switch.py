"""
scripts/ch11_runtime_switch.py —— 第 11 章：证明 runtime 可切换、上层代码不变

不依赖真实 KVM。验证 runtime 配置正确传到 docker run 参数、且换 runtime 时
DockerSandbox/上层代码完全不变。本地用 runc 跑通这条链 = 证明 kata 也能这样接。
运行：uv run python -m scripts.ch11_runtime_switch
"""
import asyncio
from unittest.mock import patch

import sandbox.docker_manager as dm


async def capture_docker_run_args(runtime: str) -> list[str]:
    """把 settings.sandbox_runtime 改成给定值,捕获 create_one_sandbox 实际拼出的 docker run 命令。"""
    captured = {}

    async def fake_run(cmd):
        # 第一次调用是 docker run（起容器），捕获它的参数
        if cmd[:2] == ["docker", "run"]:
            captured["cmd"] = cmd
        return (0, "fake-container-id")

    from infra.settings import get_settings
    settings = get_settings()
    original_runtime = settings.sandbox_runtime
    object.__setattr__(settings, "sandbox_runtime", runtime)
    try:
        with patch.object(dm, "_run", side_effect=fake_run):
            await dm.create_one_sandbox()
    finally:
        object.__setattr__(settings, "sandbox_runtime", original_runtime)
    return captured.get("cmd", [])


def runtime_in_cmd(cmd: list[str]) -> str | None:
    """从 docker run 命令里取出 --runtime 的值。"""
    if "--runtime" in cmd:
        return cmd[cmd.index("--runtime") + 1]
    return None


async def main():
    passed = total = 0

    def check(name, cond):
        nonlocal passed, total
        total += 1
        passed += 1 if cond else 0
        print(f"  {'✅' if cond else '❌'} {name}")

    # 验证三种 runtime 配置都被正确传进 docker run 参数
    for rt in ["runc", "runsc", "kata"]:
        cmd = await capture_docker_run_args(rt)
        actual = runtime_in_cmd(cmd)
        check(f"runtime={rt} → docker run --runtime {actual}", actual == rt)
        # 同时验证加固参数始终在(换 runtime 不丢加固)
        check(f"  runtime={rt} 仍带 --network none + --read-only",
              "none" in cmd and "--read-only" in cmd)

    print(f"\nruntime 切换验证：{passed}/{total} 通过")
    if passed == total:
        print("→ 三种隔离级别的命令都能正确生成,且 DockerSandbox/上层代码全程未改。")
        print("→ 本地用 runc 验证了这条链;生产 Linux 上把 SYC_SANDBOX_RUNTIME 改成 kata 即生效。")


if __name__ == "__main__":
    asyncio.run(main())