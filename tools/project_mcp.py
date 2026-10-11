"""八个绑定当前沙箱和用户的 MCP 工具，支持协议会话及独立 stdio。"""
from __future__ import annotations

import asyncio
import json
import shlex
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, AsyncIterator

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import Field
from typing import Annotated

from app.memory import MemoryService
from app.schemas import MemoryFact, MemoryModel, PreferencePatch, UserMemory, UserPreferences


class SandboxToolResult(MemoryModel):
    """受限的沙箱执行结果，不泄露宿主路径或环境变量。"""
    output: str
    exit_code: int
    truncated: bool = False


# 路径检查在容器内 realpath 之后执行，阻止 ../、绝对越界和符号链接逃逸。
_PRELUDE = '''import ast, json, os, pathlib, subprocess, sys, tempfile
data = json.loads(sys.argv[1])
root = pathlib.Path(data['root']).resolve()
def safe_path(value):
    path = pathlib.Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    path.relative_to(root)
    if any(part.startswith('.') or part == '__pycache__' for part in path.relative_to(root).parts):
        raise ValueError('hidden paths are not available')
    return path
'''


async def _execute(backend: Any, workdir: str, script: str, **data: Any) -> SandboxToolResult:
    if backend is None:
        raise ValueError("当前聊天没有开发沙箱")
    payload = json.dumps({"root": workdir, **data}, ensure_ascii=False)
    command = "python -c " + shlex.quote(_PRELUDE + script) + " " + shlex.quote(payload)
    result = await asyncio.to_thread(backend.execute, command, timeout=90)
    return SandboxToolResult(output=result.output[-16000:], exit_code=result.exit_code,
                              truncated=getattr(result, "truncated", False))


def build_project_mcp(backend: Any, workdir: str, memory: MemoryService | None,
                      user_text: str = "") -> FastMCP:
    """创建请求专属服务器；用户与沙箱身份不出现在工具可填参数中。"""
    server = FastMCP("IvyClaw-scoped-tools", instructions="只操作当前用户和当前沙箱，无法访问宿主项目或其他用户。")

    @server.tool()
    async def inspect_workspace(path: str = ".") -> SandboxToolResult:
        """列出当前沙箱目录的可见文件，定位 app/tests/skills 是否正确初始化。"""
        return await _execute(backend, workdir, '''path = safe_path(data['path'])
entries = sorted(p.name + ('/' if p.is_dir() else '') for p in path.iterdir() if not p.name.startswith('.'))[:200]
print(json.dumps(entries, ensure_ascii=False))
''', path=path)

    @server.tool()
    async def read_project_file(path: str, max_chars: Annotated[int, Field(ge=1, le=16000)] = 8000) -> SandboxToolResult:
        """读取沙箱内项目文本文件，有界输出并阻止目录或隐藏凭据读取。"""
        return await _execute(backend, workdir, '''path = safe_path(data['path'])
with path.open('r', encoding='utf-8') as file:
    print(file.read(data['max_chars']))
''', path=path, max_chars=max_chars)

    @server.tool()
    async def search_workspace(query: Annotated[str, Field(min_length=1, max_length=200)], path: str = ".",
                               max_results: Annotated[int, Field(ge=1, le=100)] = 30) -> SandboxToolResult:
        """在当前沙箱文本文件中检索已有实现，返回文件和行号。"""
        return await _execute(backend, workdir, '''base = safe_path(data['path'])
matches = []
visited = 0
for directory, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
    for name in sorted(files):
        visited += 1
        if visited > 1000 or len(matches) >= data['max_results']:
            break
        try:
            file = safe_path(str(pathlib.Path(directory) / name))
            if file.stat().st_size > 1000000:
                continue
            for number, line in enumerate(file.read_text(encoding='utf-8').splitlines(), 1):
                if data['query'].lower() in line.lower():
                    matches.append({'path': file.relative_to(root).as_posix(), 'line': number, 'text': line[:300]})
                    if len(matches) >= data['max_results']:
                        break
        except (UnicodeError, ValueError, OSError):
            continue
    if visited > 1000 or len(matches) >= data['max_results']:
        break
print(json.dumps(matches, ensure_ascii=False))
''', query=query, path=path, max_results=max_results)

    @server.tool()
    async def run_project_tests(path: str = "tests") -> SandboxToolResult:
        """仅在当前开发沙箱运行指定 tests 文件或目录，不在宿主机执行生成代码。"""
        return await _execute(backend, workdir, '''path = safe_path(data['path'])
path.relative_to(root / 'tests')
with tempfile.TemporaryFile() as output:
    try:
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--', str(path)], cwd=root,
                                stdout=output, stderr=subprocess.STDOUT, timeout=60)
        code = result.returncode
    except subprocess.TimeoutExpired:
        code = 124
    output.seek(0, 2)
    size = output.tell()
    output.seek(max(0, size - 12000))
    print(json.dumps({'exitCode': code, 'output': output.read().decode('utf-8', errors='replace'),
                      'truncated': size > 12000}, ensure_ascii=False))
    sys.exit(code)
''', path=path)

    @server.tool()
    async def check_python_syntax(path: str) -> SandboxToolResult:
        """解析沙箱 Python 文件的 AST，检查语法且不执行代码或生成 pyc。"""
        return await _execute(backend, workdir, '''path = safe_path(data['path'])
if path.suffix != '.py' or path.stat().st_size > 1000000:
    raise ValueError('expected a Python file no larger than 1 MB')
ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('syntax ok')
''', path=path)

    def require_memory() -> MemoryService:
        if memory is None:
            raise ValueError("当前运行没有配置持久记忆 Store")
        return memory

    @server.tool()
    async def recall_user_memory(query: Annotated[str, Field(max_length=1000)] = "", limit: Annotated[int, Field(ge=1, le=20)] = 8) -> UserMemory:
        """召回当前用户的 semantic 事实、episodic 经历和协作偏好。"""
        return await require_memory().recall(query, limit)

    @server.tool()
    async def remember_user_fact(fact: MemoryFact) -> MemoryFact:
        """记住用户明确表达的稳定事实；evidence 必须引用本次用户原文。"""
        return await require_memory().remember_fact(fact, user_text)

    @server.tool()
    async def set_user_preference(patch: PreferencePatch, evidence: str) -> UserPreferences:
        """按本次用户原文更新当前用户偏好，不接受其他用户标识。"""
        if not evidence or evidence not in user_text:
            raise ValueError("偏好更新必须引用本次用户原文")
        return await require_memory().update_preferences(patch)

    return server


@asynccontextmanager
async def project_mcp_session(backend: Any, workdir: str, memory: MemoryService | None,
                              user_text: str = "") -> AsyncIterator[list[Any]]:
    """通过真实 MCP initialize/list_tools/call_tool 协议加载工具并管理会话生命周期。"""
    server = build_project_mcp(backend, workdir, memory, user_text)
    async with create_connected_server_and_client_session(server, read_timeout_seconds=timedelta(seconds=120)) as session:
        tools = await load_mcp_tools(session)
        yield tools


async def serve_stdio(user_id: str, tenant_id: str, user_text: str = "") -> None:
    """为受信任的本地 stdio 客户端创建独立沙箱和固定账户记忆会话。"""
    from agent.main import build_sandbox_backend
    from infra.persistence import open_persistence
    from sandbox.manager import cleanup_sandbox
    pool, _, store = await open_persistence()
    sandbox = None
    try:
        backend, sandbox, _, workdir = await build_sandbox_backend()
        memory = MemoryService(store, user_id, tenant_id, channel="cli")
        server = build_project_mcp(backend, workdir, memory, user_text)
        await server.run_stdio_async()
    finally:
        if sandbox is not None:
            await cleanup_sandbox(sandbox)
        await pool.close()


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="IvyClaw scoped MCP stdio server")
    parser.add_argument("--user-id", required=True, help="由可信本地客户端提供的固定用户标识")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--user-text", default="", help="本次用户原文；记忆写入必须引用其中的证据")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(serve_stdio(args.user_id, args.tenant_id, args.user_text))
