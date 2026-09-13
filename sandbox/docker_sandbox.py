"""
sandbox/docker_sandbox.py —— 自托管加固容器沙箱（实现 BaseSandbox 的四个成员）
依赖：本机装好 Docker。
导入路径（官方确认）：
    from deepagents.backends.sandbox import BaseSandbox
    from deepagents.backends.protocol import (
        ExecuteResponse, FileUploadResponse, FileDownloadResponse
    )
设计：容器在创建期就以加固参数起好并常驻（sleep infinity），本类的四个成员通过 docker 命令操作那个容器：
    - id              → 容器名
    - execute         → docker exec 跑命令
    - upload_files    → docker cp 把宿主文件拷进容器
    - download_files  → docker cp 把容器文件拷出来读字节
注意：本类实现同步方法;BaseSandbox 会用 asyncio.to_thread 把它们包成异步(aexecute 等),
      所以 agent 走 ainvoke 时不阻塞事件循环。
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from deepagents.backends.sandbox import BaseSandbox
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileUploadResponse,
    FileDownloadResponse,
)

from infra.logging import get_logger

logger = get_logger()


class DockerSandbox(BaseSandbox):
    """在一个加固 Docker 容器里执行命令、传输文件。容器生命周期由 docker_manager.py 管。"""

    def __init__(self, container_id: str, workdir: str = "/home/agent"):
        self.container_id = container_id
        self.workdir = workdir

    # ---------- 必须实现 1：唯一标识 ----------
    @property
    def id(self) -> str:
        return self.container_id

    # ---------- 必须实现 2：执行命令（同步）----------
    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """在容器里跑一条 shell 命令，返回 ExecuteResponse（output + exit_code + truncated）。"""
        proc = subprocess.run(
            ["docker", "exec", "-w", self.workdir, self.container_id, "sh", "-lc", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # 合并 stderr 到 stdout
            timeout=timeout,
        )
        text = proc.stdout.decode("utf-8", errors="replace")
        truncated = len(text) > 8000
        return ExecuteResponse(
            output=text[-8000:],        # 截断尾部，避免巨量输出灌爆上下文
            exit_code=proc.returncode,
            truncated=truncated,
        )

    # ---------- 必须实现 3：上传文件（write_file/edit_file 底层依赖它）----------
    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """把 [(沙箱内绝对路径, 字节内容), ...] 写进容器。逐个处理，支持部分成功（不抛异常）。"""
        results: list[FileUploadResponse] = []
        for path, content in files:
            try:
                parent = os.path.dirname(path)
                if parent:
                    subprocess.run(
                        ["docker", "exec", self.container_id, "mkdir", "-p", parent],
                        #在 Docker 容器里面确保父目录存在。如果目录不存在，就创建；如果已经存在，也不要报错
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )

                cp = subprocess.run(
                    [
                        "docker", "exec", "-i",
                        self.container_id,
                        "sh", "-c",
                        'cat > "$1"',
                        "sh",
                        path,
                    ],
                    input=content,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )

                if cp.returncode == 0:
                    results.append(FileUploadResponse(path=path))
                else:
                    err = cp.stdout.decode("utf-8", errors="replace") or "upload_failed"
                    results.append(FileUploadResponse(path=path, error=err))
            except Exception as e:  # noqa: BLE001 协议要求部分成功,不抛异常
                results.append(FileUploadResponse(path=path, error=str(e)))
        return results

    # ---------- 必须实现 4：下载文件 ----------
    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """从容器读出 paths 指定的文件字节。逐个处理，支持部分成功（不抛异常）。"""
        results: list[FileDownloadResponse] = []
        for path in paths:
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp_path = tmp.name
                cp = subprocess.run(
                    ["docker", "cp", f"{self.container_id}:{path}", tmp_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                if cp.returncode == 0:
                    with open(tmp_path, "rb") as f:
                        data = f.read()
                    results.append(FileDownloadResponse(path=path, content=data))
                else:
                    results.append(
                        FileDownloadResponse(path=path, content=None, error="file_not_found")
                    )
            except Exception as e:  # noqa: BLE001
                results.append(FileDownloadResponse(path=path, content=None, error=str(e)))
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        return results