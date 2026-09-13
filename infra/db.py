"""infra/db.py —— 异步 Postgres 连接池（psycopg3 AsyncConnectionPool）

工程化要点：
- 池在服务启动时建一次、全程复用（见 api/app.py lifespan）；
- kwargs 带 autocommit=True / row_factory=dict_row —— LangGraph 的 Async saver/store
  用这个池时的官方硬要求，缺了会出错或行为异常；
- prepare_threshold=0：配合 pgbouncer 等连接池中间件时避免 prepared statement 问题。
"""

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from infra.settings import get_settings

def build_pg_pool() -> AsyncConnectionPool:
    """构建（但不打开）异步 Postgres 连接池。open() 在 lifespan 里做。"""
    s = get_settings()
    return AsyncConnectionPool(
        conninfo=s.database_url,
        min_size=s.pg_pool_min,
        max_size=s.pg_pool_max,
        open=False,
        kwargs={
            "autocommit" : True,
            "row_factory" : dict_row,
            "prepare_threshold": 0,
        },
        timeout=10
    )










