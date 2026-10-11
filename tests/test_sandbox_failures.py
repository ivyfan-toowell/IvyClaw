"""初始化或复制失败后不得遗留沙箱资源。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sandbox import docker_manager
from sandbox import manager
from agent import main
from sandbox.docker_sandbox import DockerSandbox
import json


@pytest.mark.asyncio
async def test_seed_failure_cleans_created_sandbox(monkeypatch) -> None:
    """Agent 尚未构建，seed 出错也回收已经创建的容器。"""
    sandbox = object()
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(sandbox_provider="docker"))
    monkeypatch.setattr(docker_manager, "create_one_sandbox", AsyncMock(return_value=sandbox))
    monkeypatch.setattr(docker_manager, "seed_project", AsyncMock(side_effect=RuntimeError("seed failed")))
    cleanup = AsyncMock()
    monkeypatch.setattr(manager, "cleanup_sandbox", cleanup)
    with pytest.raises(RuntimeError, match="seed failed"):
        await main.build_sandbox_backend()
    cleanup.assert_awaited_once_with(sandbox)


@pytest.mark.asyncio
async def test_reviewer_export_failure_cleans_copy(monkeypatch) -> None:
    """只读副本创建后导出失败，由创建函数本身回收。"""
    monkeypatch.setattr(docker_manager, "_run", AsyncMock(return_value=(0, "created")))
    result = SimpleNamespace(returncode=1, stderr=b"export failed")
    monkeypatch.setattr(docker_manager.subprocess, "run", lambda *args, **kwargs: result)
    destroy = AsyncMock()
    monkeypatch.setattr(docker_manager, "destroy_sandbox", destroy)
    with pytest.raises(RuntimeError, match="导出源沙箱"):
        await docker_manager.create_readonly_sandbox(SimpleNamespace(container_id="source"))
    assert destroy.await_count == 1


def test_execute_preserves_image_environment(monkeypatch) -> None:
    """非 login shell 保留镜像 PATH，能使用预装虚拟环境而非系统 Python。"""
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"ok")

    monkeypatch.setattr("sandbox.docker_sandbox.subprocess.run", run)
    assert DockerSandbox("test").execute("python -m pytest").exit_code == 0
    assert calls[0][-3:] == ["sh", "-c", "python -m pytest"]


def test_execute_preserves_large_file_protocol_response(monkeypatch) -> None:
    """超过旧 8,000 字符限制的协议 JSON 必须完整，否则文件工具无法解析。"""
    content = "中文 file contents " * 1000
    payload = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
    monkeypatch.setattr("sandbox.docker_sandbox.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=payload))
    result = DockerSandbox("test").execute("backend file read")
    assert json.loads(result.output)["content"] == content
    assert not result.truncated
