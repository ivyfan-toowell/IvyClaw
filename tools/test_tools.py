"""tools/test_tools.py —— 跑测试的封装工具

⚠️ 重要：本地开发阶段这里用 subprocess 跑 pytest 只是过渡。
真正"安全地让 DevMate 跑测试"要在沙箱里（第 6 章）——绝不能在生产宿主机上直接跑模型生成的命令。
"""
import asyncio
from langchain.tools import tool

@tool()
async def run_pytest(path: str = "test/") -> str:
    """运行 pytest 跑测试，返回测试结果摘要。path 指定测试目录/文件。
    用于在改完代码后验证是否通过测试。"""
    proc = await asyncio.create_subprocess_exec(
        "pytest",
        path,
        "-q",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return out.decode()[-3000:]