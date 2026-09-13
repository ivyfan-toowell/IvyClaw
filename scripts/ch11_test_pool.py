"""scripts/ch11_test_pool.py —— 第 11 章：沙箱池行为验证（假沙箱,测逻辑）

验三条：① 同时活跃沙箱峰值 ≤ max_size；② 每个任务拿到全新独立实例（隔离优先）；
③ 销毁数 == 创建数（用完即弃,不泄漏）。
运行：uv run python -m scripts.ch11_test_pool
"""
import asyncio
import itertools
from unittest.mock import patch

_counter = itertools.count()
_destroyed = []


class FakeSandbox:
    def __init__(self):
        self.id_num = next(_counter)
        self.workdir = "/home/agent"
    @property
    def container_id(self):
        return f"fake-{self.id_num}"


async def _fake_create():
    await asyncio.sleep(0.05)
    return FakeSandbox()


async def _fake_seed(sb):
    return None


async def _fake_destroy(sb):
    _destroyed.append(sb.id_num)


async def main():
    # 用 mock.patch 替换池里的创建/seed/销毁,聚焦池逻辑(标准做法,比手动改模块属性稳)
    with patch("sandbox.pool.create_one_sandbox", side_effect=_fake_create), \
         patch("sandbox.pool.seed_project", side_effect=_fake_seed), \
         patch("sandbox.pool.destroy_sandbox", side_effect=_fake_destroy):
        from sandbox.pool import SandboxPool

        pool = SandboxPool(max_size=3)
        seen_ids, max_concurrent, active = set(), 0, 0
        lock = asyncio.Lock()

        async def task(n):
            nonlocal max_concurrent, active
            async with pool.acquire() as (sb, workdir):
                async with lock:
                    active += 1
                    max_concurrent = max(max_concurrent, active)
                    seen_ids.add(sb.id_num)
                await asyncio.sleep(0.1)
                async with lock:
                    active -= 1

        await asyncio.gather(*[task(i) for i in range(10)])

    print(f"  并发峰值：{max_concurrent}（上限 3）",
          "✅" if max_concurrent <= 3 else "❌ 超过上限")
    print(f"  每任务全新实例：创建 {len(seen_ids)} 个 == 任务数 10？",
          "✅ 隔离优先(无复用串数据)" if len(seen_ids) == 10 else "⚠️ 有复用")
    print(f"  用完即弃：销毁 {len(_destroyed)} 个 == 创建数？",
          "✅" if len(_destroyed) == len(seen_ids) else "❌ 有泄漏")


if __name__ == "__main__":
    asyncio.run(main())