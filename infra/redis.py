"""infra/redis.py —— 异步 Redis 连接池（redis.asyncio）

redis-py 自带异步接口与连接池。这里建一个全局复用的客户端。
后半的任务队列（arq）/ 限流会用到它。
"""

from redis.asyncio import Redis, ConnectionPool
from infra.settings import get_settings

def build_redis(_pool_holder: dict | None = None) -> Redis:
    """构建异步 Redis 客户端（内部带连接池）。在 lifespan 里建一次、复用。"""
    s = get_settings()
    pool = ConnectionPool.from_url(
        s.redis_url,
        max_connections=s.redis_pool_max,
        decode_responses=True,
    )

    return Redis(connection_pool=pool)



