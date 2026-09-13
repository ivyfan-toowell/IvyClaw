"""
sandbox/pool.py —— 隔离优先的沙箱池（面向 BaseSandbox 接口）
- 并发上限：信号量保证同时存在的沙箱不超过 max_size；
- 隔离优先：每任务拿干净沙箱，release 时销毁（用完即弃），不串数据；
- 交回可用上下文 (backend, workdir)，不是裸 sandbox；
- async with acquire() 保证异常也归还/销毁,不泄漏。
"""
import asyncio
from contextlib import asynccontextmanager

from infra.settings import get_settings
from infra.logging import get_logger
from sandbox.docker_manager import create_one_sandbox, seed_project, destroy_sandbox

from obs.metrics import SANDBOX_ACTIVE

logger = get_logger()


class SandboxPool:
    def __init__(self, max_size: int):
        self._sem = asyncio.Semaphore(max_size)   # 并发上限闸
        self._max = max_size

    @asynccontextmanager
    async def acquire(self):
        """借一个干净沙箱；用完销毁（隔离优先）。yield (backend, workdir)。"""
        await self._sem.acquire()                  # 占名额（到上限就在这里等）
        sandbox = None
        active_counted = False

        try:
            sandbox = await create_one_sandbox()   # 全新、加固、隔离
            await seed_project(sandbox)            # 池内部 seed 好

            SANDBOX_ACTIVE.inc()
            active_counted = True

            yield sandbox, sandbox.workdir         # ← 交回可用上下文
        finally:
            if sandbox is not None:
                await destroy_sandbox(sandbox)     # 用完即弃：销毁,不复用、不串数据

            if active_counted:
                SANDBOX_ACTIVE.dec()

            self._sem.release()


_pool: SandboxPool | None = None


def get_sandbox_pool() -> SandboxPool:
    global _pool
    if _pool is None:
        _pool = SandboxPool(max_size=get_settings().sandbox_pool_size)
    return _pool