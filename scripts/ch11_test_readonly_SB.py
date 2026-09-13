"""scripts/ch11_test_readonly_B.py —— 第 11 章：Reviewer 沙箱物理只读验证

验证目标：
1. 创建普通 DockerSandbox
2. 写入一个测试文件
3. 基于它创建 reviewer 只读沙箱
4. 验证 reviewer 可以读取文件
5. 验证 reviewer 通过 execute 也无法修改文件

运行：
uv run python -m scripts.ch11_test_readonly_SB
"""

import asyncio

from sandbox.docker_manager import (
    create_one_sandbox,
    create_readonly_sandbox,
    destroy_sandbox,
)


async def main():
    sandbox = None
    readonly = None

    try:
        # ① 创建普通可写沙箱
        sandbox = await create_one_sandbox()
        # ② 在源沙箱写一个文件
        result = sandbox.execute('echo "original" > /home/agent/test.txt')
        print("源沙箱写入：", result.exit_code, result.output)
        # ③ 创建 reviewer 专用只读沙箱
        readonly = await create_readonly_sandbox(sandbox)
        # ④ 验证：可以读取
        result = readonly.execute("cat /home/agent/test.txt")
        print("只读沙箱读取：", result.exit_code, result.output)
        # ⑤ 验证：不能修改
        result = readonly.execute('echo "hacked" > /home/agent/test.txt')
        print("只读沙箱写入：", result.exit_code, result.output)
        # ⑥ 再读一次，确认内容没被改
        result = readonly.execute("cat /home/agent/test.txt")
        print("最终文件内容：", result.output)

        print("\n========== 验证结果 ==========")

        if result.output.strip() == "original":
            print("✅ Reviewer 只读沙箱生效：文件未被修改")
        else:
            print("❌ Reviewer 只读沙箱失效：文件被修改")

    finally:
        # ⑦ 两个沙箱都清理掉
        if readonly is not None:
            await destroy_sandbox(readonly)
        if sandbox is not None:
            await destroy_sandbox(sandbox)


if __name__ == "__main__":
    asyncio.run(main())