"""sandbox/manager.py —— 沙箱接入与生命周期管理（"沙箱即工具"模式）

这个模块负责：把 Agent 的"手脚"放进一个隔离的远程沙箱里。
Agent 在沙箱里读写文件、跑命令（pytest、python 等），而宿主机/主进程保持干净、
不被 Agent 生成的代码污染，密钥也不会泄漏进沙箱。

工程化要点（来自官方 sandboxes 文档）：
- 按 thread_id 隔离：每个会话（一个 Issue）对应一个独立沙箱，get-or-create 复用；
- TTL 自动回收：空闲沙箱由 provider（Daytona）自动清理，避免一直挂着计费；
- 密钥绝不进沙箱：API key 只在主进程 build_model() 里用（见 agent/main.py 与本章 3.7 安全节）。

注意（高并发）：本章是"每会话一个沙箱"的基础形态。后半做高并发服务时，
要升级成"沙箱池 + 并发隔离 + 超时回收"（第 11 章），并配合任务队列复用沙箱。
"""
from __future__ import annotations

from pathlib import Path

from daytona import ListSandboxesQuery

from infra.logging import get_logger

logger = get_logger()


def _collect_project_files(
    root: Path,
    dest_root: str,
    subdirs: list[str],
    extra_files: list[str],
) -> list[tuple[str, bytes]]:
    """把宿主机项目里要 seed（预置）进沙箱的文件，收集成 upload_files 需要的格式。

    返回值：[(沙箱内绝对路径, 文件字节内容), ...]
    例如：[("/home/daytona/app/pricing.py", b"def price()..."), ...]

    为什么要这个函数：
      沙箱刚创建时是个空环境，里面没有你的项目代码。Agent 要改 app/、跑 tests/、
      用 skills/，就得先把这些文件从宿主机"上传"进去。这一步就是把"哪些文件、
      放到沙箱里的什么路径"整理成官方 upload_files() 能直接吃的列表。

    两个硬性约束（官方要求，踩了会报错）：
      1) upload_files 的目标路径必须是【绝对路径】；
      2) 文件内容必须是 bytes（所以下面用 read_bytes() 而不是 read_text()）。

    dest_root 是沙箱的【工作目录】（Daytona 默认 /home/daytona）——
    一定要把项目放到它下面，不要往 / 根目录写：
    沙箱默认用户没有 root 权限，往根目录 mkdir 会直接 'permission denied'。
    """
    items: list[tuple[str, bytes]] = []
    dest_root = dest_root.rstrip("/")   # 去掉结尾斜杠，规范化，避免后面拼出 // 双斜杠

    # 1) 处理指定的子目录：递归遍历里面所有文件并上传
    #    （跳过 __pycache__ 缓存目录 和 . 开头的隐藏文件/目录，避免把垃圾传进去）
    for sub in subdirs:
        base = root / sub          # 宿主机上这个子目录的绝对路径
        if not base.exists():      # 项目里没有这个目录就跳过（容错，不报错）
            continue
        for p in base.rglob("*"):  # rglob("*") = 递归列出该目录下所有条目（含子目录里的）
            # 三个条件同时满足才上传：
            #   - 是"文件"（跳过目录本身）
            #   - 路径里不含 __pycache__（排除编译缓存）
            #   - 从项目根算起，各级目录/文件名都不以 . 开头（排除 .git/.venv 等隐藏内容）
            if p.is_file() and "__pycache__" not in p.parts and not any(
                part.startswith(".") for part in p.relative_to(root).parts
            ):
                # 相对项目根的路径，转成正斜杠形式（沙箱是 Linux，路径分隔用 /）
                rel = p.relative_to(root).as_posix()
                # 拼成 (沙箱内绝对路径, 文件字节)；read_bytes() 满足"内容必须是 bytes"
                items.append((f"{dest_root}/{rel}", p.read_bytes()))

    # 2) 处理单独列出的根级文件（比如仓库记忆文件 AGENTS.md，它不在某个子目录里）
    for fname in extra_files:
        f = root / fname
        if f.is_file():            # 存在才传（容错）
            items.append((f"{dest_root}/{fname}", f.read_bytes()))

    return items


def seed_project_into_sandbox(backend, sandbox, root: Path) -> str:
    """把项目源码/技能/记忆 seed（预置）进沙箱（Agent 跑之前必须做这一步）。

    返回：沙箱的工作目录（如 /home/daytona），后面拼 skills/memory 路径要用。

    为什么必须 seed：
      沙箱默认是空环境——不 seed 的话，Agent 既看不到 app/ 也找不到 skills，
      于是 coder 子代理会"写不进文件"、skills 会报 path_not_found。
      （反过来：如果你遇到这两个症状，八成就是忘了 seed、或 seed 到了错误的目录。）

    关键坑：要 seed 到沙箱的【工作目录】（Daytona 默认 /home/daytona），
      不要写死 /workspace——往 / 根目录建目录会因无 root 权限报
      'mkdir /workspace: permission denied'。所以下面先去问沙箱它的真实工作目录。
    """
    # 先取沙箱的真实工作目录（Daytona 是 WORKDIR 或用户家目录，通常 /home/daytona）；
    # 不同版本/镜像可能没有这个方法或抛异常，所以用 try 兜底成 /home/daytona。
    try:
        workdir = sandbox.get_workspace_root_dir()
    except Exception:
        workdir = "/home/daytona"   # 兜底默认值
    workdir = (workdir or "/home/daytona").rstrip("/")   # 防止返回 None/空串，并去尾斜杠

    # 把要预置的文件整理成 upload_files 的格式：
    #   - 上传 app/（被测项目）、tests/（测试）、skills/（技能库）三个目录的内容
    #   - 外加根级的 AGENTS.md（仓库记忆）
    files = _collect_project_files(
        root,
        dest_root=workdir,
        subdirs=["app", "tests", "skills"],
        extra_files=["AGENTS.md","pyproject.toml", "uv.lock"],
    )
    # 一个文件都没收集到 → 大概率是项目结构不对（app/ tests/ skills/ 全空），
    # 这里只告警不报错，让流程继续（但 Agent 多半会因为没文件而干不了活）。
    if not files:
        logger.warning("没有可 seed 的项目文件（app/ tests/ skills/ 都为空？）")
        return workdir

    # 真正执行上传。官方 API：upload_files([(绝对路径, bytes), ...])
    # 这些绝对路径都在工作目录下，当前用户有写权限，所以不会 permission denied。
    backend.upload_files(files)
    logger.info("已 seed {} 个文件进沙箱工作目录 {}", len(files), workdir)
    return workdir



def install_sandbox_dependencies(backend, workdir: str) -> None:
    """在新建沙箱中安装项目完整依赖。"""
    logger.info("开始安装沙箱项目依赖")

    result = backend.execute(
        f"cd {workdir} && uv sync"
    )

    if getattr(result, "exit_code", 1) == 0:
        logger.info("沙箱项目依赖安装完成")
    else:
        logger.error(
            "沙箱项目依赖安装失败：{}",
            getattr(result, "stderr", result),
        )



def get_or_create_sandbox_backend(thread_id: str, project_root: Path | None = None):
    """按 thread_id 获取或创建一个沙箱后端（这里用 Daytona 做示例），新建时顺带 seed 项目。

    返回四元组 (backend, sandbox, client, workdir)：
      - backend  传给 create_deep_agent(backend=...)，让 Agent 拥有文件工具 + execute；
      - sandbox  沙箱对象，用于生命周期管理（stop/delete）；
      - client   Daytona 客户端，同样用于管理/查询；
      - workdir  沙箱工作目录（如 /home/daytona），用于拼 skills / memory 的绝对路径。

    凭据来源：真实 provider 凭据从环境变量读（如 DAYTONA_API_KEY），绝不写死在代码里。

    实现说明（这些都是"各版本都稳"的写法，专门避开会随版本变动的坑）：
    - 查已有沙箱用 client.list(labels=...)，不用 find_one——后者在某些版本不存在/会抛异常；
    - 自动回收（TTL）通过【客户端】配置 auto_delete_interval，放在 DaytonaConfig 里，
      不要塞进 create() 的 params（塞错位置会引发奇怪的编码/请求错误）；
    - labels 只用纯 ASCII（如 thread_id），别放中文——labels 会进 HTTP header，
      非 latin-1 字符会触发 UnicodeEncodeError。
    """
    # 延迟到函数内部再 import：避免没装/没用到沙箱时，模块一加载就报 ImportError。
    from daytona import Daytona, DaytonaConfig
    from langchain_daytona import DaytonaSandbox

    # 项目根目录：没显式传就用本文件往上两级（sandbox/ 的上一级，即仓库根 shanyang-claw/）。
    root = project_root or Path(__file__).resolve().parent.parent

    # 创建 Daytona 客户端：
    #   - api_key / target 等会自动从环境变量读（见 3.3），前提是入口已经 load_dotenv()；
    #   - auto_delete_interval=60 = 沙箱"持续停止"满 60 分钟后自动删除（TTL，单位：分钟）。
    client = Daytona(DaytonaConfig(auto_delete_interval=60))

    label = {"thread_id": thread_id}   # 纯 ASCII 标签，安全，用它来认领/复用本会话的沙箱

    # ========== get-or-create：先按 label 查，有就复用，没有就新建 ==========
    is_new = False
    sandbox = None
    try:
        existing = client.list(ListSandboxesQuery(labels=label))  # 查所有打了这个 label 的沙箱
        # 不同版本返回值可能是：①一个 list；②一个带 .sandboxes 属性的分页对象；
        # ③一个 generator（迭代器）。下面统一把它收敛成一个真正的 list：
        raw = getattr(existing, "sandboxes", existing)   # 是分页对象就取 .sandboxes，否则用本身
        items = list(raw) if raw is not None else []     # ★ 关键：强制转成 list！
        # ★ 为什么要 list(raw)：如果 client.list() 返回的是 generator，
        #   直接写 items[0] 会报 "'generator' object is not subscriptable"
        #   ——generator 不支持下标取值（你之前那次报错就栽在这）。转成 list 就安全了。
        #   （若你只想保留原逻辑，把这两行换回： items = getattr(existing, "sandboxes", existing) or []）
        if items:
            sandbox = items[0]

            try:
                sandbox.start()
                logger.info("复用已有沙箱并确保已启动：thread_id={}", thread_id,)
            except Exception as e:
                logger.warning("已有沙箱无法启动，将重新创建：{}", e,)
                sandbox = None

    except Exception as e:  # noqa: BLE001 查不到/接口差异 都当作"没有"，走下面的新建分支
        logger.info("查询已有沙箱失败（将新建）：{}", e)

    # 没查到可复用的沙箱 → 新建一个
    if sandbox is None:
        sandbox = client.create()            # 最朴素的 create()，用默认镜像建一个新沙箱
        try:
            sandbox.set_labels(label)        # 建好后打上 label，方便【下一次】按 label 复用
        except Exception:  # noqa: BLE001 打 label 失败不影响本次使用，忽略即可
            pass
        is_new = True
        logger.info("新建沙箱：thread_id={}（TTL=60min）", thread_id)

    # 用沙箱对象包一层 LangChain 的后端适配器，它会自动给 Agent 提供文件工具 + execute。
    backend = DaytonaSandbox(sandbox=sandbox)

    # 新建 vs 复用，对工作目录的处理不同：
    if is_new:
        # 1. 把项目文件 seed 进新沙箱
        workdir = seed_project_into_sandbox(backend, sandbox, root)
        # 2. 给新沙箱安装测试依赖
        install_sandbox_dependencies(backend, workdir)

    else:
        # 复用：项目早就 seed 过了，只需重新问一下工作目录用于拼路径（同样做兜底）
        try:
            workdir = (sandbox.get_workspace_root_dir() or "/home/daytona").rstrip("/")
        except Exception:
            workdir = "/home/daytona"

    return backend, sandbox, client, workdir

def download_artifacts(
        backend,
        sandbox_paths:list[str],
) -> dict[str, bytes]:
    """从沙箱取回指定文件（agent 跑完后用）。返回 {沙箱路径: 字节内容}。

    官方 download_files 返回结果含 .path / .content(bytes) / .error。
    """
    out: dict[str, bytes] = {}
    results = backend.download_files(sandbox_paths)
    for result in results:
        if getattr(result, "content", None) is not None:
            out[result.path] = result.content
        else:
            logger.warning("取回失败 {}：{}", getattr(result, "path", "?"), getattr(result, "error", "?"))
    return out



async def cleanup_sandbox(sandbox) -> None:
    """统一清理 Docker / Daytona 沙箱。"""

    from sandbox.docker_sandbox import DockerSandbox

    if isinstance(sandbox, DockerSandbox):
        from sandbox.docker_manager import destroy_sandbox
        await destroy_sandbox(sandbox)
        return

    # Daytona 原生 sandbox
    stop = getattr(sandbox, "stop", None)
    if callable(stop):
        stop()
        return

    raise TypeError(f"不支持的 sandbox 类型：{type(sandbox)!r}")

















