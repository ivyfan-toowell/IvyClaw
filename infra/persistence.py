"""infra/persistence.py —— 建异步持久化资源（saver/store），供服务与独立进程共用

第 8 章把建池/saver/store 写在了 FastAPI lifespan 里。但飞书长连接接收端是
独立进程、不经过 lifespan，需要自己建一份。于是把这段抽出来两边复用——
这也修正了"独立进程 from api.app import app 拿不到 app.state"的错误接法。
"""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from infra.db import build_pg_pool


async def open_persistence():
    """
    打开连接池并构造 saver/store（已 setup）。返回 (pool, checkpointer, store)。
    调用方负责在退出时 await pool.close()。
    """
    pool = build_pg_pool()
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    store = AsyncPostgresStore(pool)
    await checkpointer.setup()
    await store.setup()
    return pool, checkpointer, store