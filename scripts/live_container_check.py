"""真实隔离容器 smoke：项目 seed、MCP 执行测试、审查副本和内存检查。"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session

from sandbox.docker_manager import create_one_sandbox, create_readonly_sandbox, destroy_sandbox, seed_project
from tools.project_mcp import build_project_mcp


async def check() -> dict[str, Any]:
    """使用正式沙箱初始化与 MCP 代码进行无外部模型的真实容器检查。"""
    sandbox = await create_one_sandbox()
    readonly = None
    report: dict[str, Any] = {"sandbox": sandbox.container_id, "tools": {}}
    try:
        await seed_project(sandbox)
        read = await asyncio.to_thread(sandbox.read, sandbox.workdir + "/app/memory.py", offset=0, limit=1000)
        assert read.error is None and len(read.file_data["content"]) > 8000
        report["largeFileProtocolRead"] = True
        server = build_project_mcp(sandbox, sandbox.workdir, None)
        async with create_connected_server_and_client_session(server) as session:
            report["toolCount"] = len((await session.list_tools()).tools)
            for name, arguments in [
                ("inspect_workspace", {}),
                ("read_project_file", {"path": "app/pricing.py"}),
                ("search_workspace", {"query": "quote_total", "path": "app"}),
                ("check_python_syntax", {"path": "app/pricing.py"}),
                ("run_project_tests", {"path": "tests"}),
            ]:
                result = await session.call_tool(name, arguments)
                report["tools"][name] = result.structuredContent
                print(name + ": " + json.dumps(result.structuredContent, ensure_ascii=False), flush=True)
                assert not result.isError and result.structuredContent["exitCode"] == 0, name
        readonly = await create_readonly_sandbox(sandbox)
        read = await asyncio.to_thread(readonly.execute, "cat app/pricing.py")
        write = await asyncio.to_thread(readonly.execute, "printf blocked > app/pricing.py")
        assert read.exit_code == 0 and write.exit_code != 0
        report["reviewerReadonly"] = True
        for name in (sandbox.container_id, readonly.container_id):
            result = await asyncio.to_thread(subprocess.run, ["docker", "exec", name, "sh", "-c",
                "cat /sys/fs/cgroup/memory.peak; cat /sys/fs/cgroup/memory.events"], capture_output=True, text=True, check=True)
            report[name] = result.stdout
        report["passed"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return report
    finally:
        for name in (sandbox.container_id, readonly.container_id if readonly else None):
            if name:
                result = await asyncio.to_thread(subprocess.run, ["docker", "exec", name, "sh", "-c",
                    "cat /sys/fs/cgroup/memory.peak; cat /sys/fs/cgroup/memory.events"], capture_output=True, text=True)
                report[name] = result.stdout
                print(name + ": " + result.stdout, flush=True)
        path = Path("logs/live_container_check.json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if readonly is not None:
            await destroy_sandbox(readonly)
        await destroy_sandbox(sandbox)


if __name__ == "__main__":
    report = asyncio.run(check())
    path = Path("logs/live_container_check.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
