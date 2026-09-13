"""sandbox/docker_manager.py —— 加固容器的创建/seed/销毁

runtime 参数是隔离级别开关：runc(加固容器) / runsc(gVisor) / kata(microVM)。
换 runtime 就换隔离级别，DockerSandbox 代码不变（见第 4 节）。
这里用 asyncio.create_subprocess_exec 管容器生命周期(应用自己的异步逻辑)。
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from infra.settings import get_settings
from infra.logging import get_logger
from sandbox.docker_sandbox import DockerSandbox
import asyncio
import subprocess

import time
from obs.metrics import SANDBOX_CREATE_DURATION


logger = get_logger()


async def _run(cmd: list[str]) -> tuple[int, str]:
    def _sync_run():
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        output = result.stdout or result.stderr
        return result.returncode, output.strip()

    return await asyncio.to_thread(_sync_run)



async def create_one_sandbox() -> DockerSandbox:
    """以加固参数起一个常驻容器，返回 DockerSandbox。"""

    start = time.perf_counter()
    s = get_settings()
    name = f"ivc-sbx-{uuid.uuid4().hex[:12]}"
    workdir = s.sandbox_workdir

    # tmpfs 工作目录：可写 + 可执行 + 限大小 + 属主对齐非 root 用户(uid=1000)
    tmpfs_opt = f"{workdir}:rw,exec,size=512m,uid=1000"

    code, out = await _run([
        "docker", "run", "-d", "--name", name,
        "--runtime", s.sandbox_runtime,             # ← 换它即换隔离级别
        "--network", "none",                        # 断网
        "--cap-drop", "ALL",                        # 丢能力
        "--security-opt", "no-new-privileges",      # 禁提权
        "--read-only",                              # 只读根
        "--tmpfs", tmpfs_opt,                       # 唯一可写区
        "--tmpfs", "/tmp:rw,exec,size=128m,uid=1000",  # 额外给 /tmp 可写(部分工具需要)
        "--memory", s.sandbox_mem_limit,
        "--memory-swap", s.sandbox_mem_limit,
        "--pids-limit", str(s.sandbox_pids_limit),
        "--cpus", s.sandbox_cpus,
        "--user", "1000:1000",                      # 非 root
        "-w", workdir,
        s.sandbox_image, "sleep", "infinity",       # 常驻，等 docker exec
    ])
    if code != 0:
        raise RuntimeError(f"起沙箱容器失败：{out}")
    logger.info("加固容器已起：{}（runtime={}）", name, s.sandbox_runtime)
    SANDBOX_CREATE_DURATION.observe(time.perf_counter() - start)
    return DockerSandbox(container_id=name, workdir=workdir)



# sandbox/docker_manager.py（追加：只读 reviewer 用的沙箱）
async def create_readonly_sandbox(source_sandbox: DockerSandbox) -> DockerSandbox:
    """
    给 reviewer 起一个只读容器：把 source_sandbox 的工作目录内容复制进来后设为只读。
    实现：① 起一个新容器；② 从源容器把代码 cp 出来再 cp 进新容器；
         ③ 在新容器内 chmod -R a-w 工作目录,使 execute 跑 echo>file 也写不进。
    这样 reviewer 即使用 execute 也改不了代码——靠文件系统权限,不靠 prompt。
    """
    import tempfile
    s = get_settings()
    name = f"ivc-ro-{uuid.uuid4().hex[:12]}"
    workdir = s.sandbox_workdir
    code, out = await _run([
        "docker", "run", "-d", "--name", name,
        "--runtime", s.sandbox_runtime,
        "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--read-only",
        "--tmpfs", f"{workdir}:rw,exec,size=512m,uid=1000",
        "--memory", s.sandbox_mem_limit, "--memory-swap", s.sandbox_mem_limit,
        "--pids-limit", str(s.sandbox_pids_limit), "--cpus", s.sandbox_cpus,
        "--user", "1000:1000", "-w", workdir,
        s.sandbox_image, "sleep", "infinity",
    ])
    if code != 0:
        raise RuntimeError(f"起只读沙箱失败：{out}")
    ro = DockerSandbox(container_id=name, workdir=workdir)
    # 把源容器代码搬进来(经宿主中转),然后把工作目录设为不可写
    # 把源容器代码搬出来，再通过 upload_files 写进 reviewer 容器

    import subprocess

    # 源沙箱工作目录 → 打成 tar 数据
    proc = await asyncio.to_thread(
        subprocess.run,
        ["docker", "exec", source_sandbox.container_id,"tar", "-C", workdir, "-cf", "-", "."],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"导出源沙箱代码失败：{proc.stderr.decode(errors='replace')}")

    # tar 数据 → reviewer 沙箱工作目录
    proc2 = await asyncio.to_thread(
        subprocess.run,
        ["docker", "exec", "-i", name, "tar", "-C", workdir, "-xf", "-"],
        input=proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc2.returncode != 0:
        raise RuntimeError(f"写入 reviewer 沙箱失败：{proc2.stderr.decode(errors='replace')}")


    # chmod 去掉写位(用 root 改,因为非 root 改不动自己没权限的位)
    code, out = await _run(["docker", "exec","-u", "1000:1000",name,"chmod", "-R", "a-w",workdir])
    if code != 0:
        raise RuntimeError(f"设置 reviewer 只读失败：{out}")
    logger.info("只读 reviewer 沙箱已起：{}", name)
    return ro


async def seed_project(
    sandbox: DockerSandbox,
    root: Path | None = None,
    subdirs: tuple[str, ...] = ("app", "tests", "skills"),
    extra_files: tuple[str, ...] = ("AGENTS.md",),
) -> None:
    """
    把宿主项目 seed 进容器工作目录（docker cp）。
    与第 6 章一致：不 seed 的话沙箱是空的，coder 写不进文件、skills 报 path_not_found。
    """
    root = root or Path(__file__).resolve().parent.parent
    workdir = sandbox.workdir

    files_to_upload: list[tuple[str, bytes]] = []

    # ① 收集 app / tests / skills 里的所有文件
    for sub in subdirs:
        base = root / sub

        if not base.exists():
            continue

    for fp in base.rglob("*"):
        if fp.is_file():
            relative_path = fp.relative_to(root).as_posix()
            target_path = f"{workdir}/{relative_path}"

            files_to_upload.append((target_path, fp.read_bytes()))

    # ② 收集 AGENTS.md 这类额外文件
    for name in extra_files:
        fp = root / name

        if fp.is_file():
            files_to_upload.append(
                (f"{workdir}/{name}", fp.read_bytes())
            )

    # ③ 使用已经验证成功的 upload_files 写入容器
    results = await asyncio.to_thread(sandbox.upload_files,files_to_upload)

    # ④ 检查有没有失败
    errors = [r for r in results if r.error]
    if errors:
        raise RuntimeError(f"seed 项目失败：{errors}")
    logger.info("项目已 seed 进容器 {}", sandbox.container_id)




async def destroy_sandbox(sandbox: DockerSandbox) -> None:
    """销毁容器（用完即弃）。tmpfs 工作目录随容器一起消失，不残留。"""
    await _run(["docker", "rm", "-f", sandbox.container_id])
    logger.info("容器已销毁：{}", sandbox.container_id)

