"""infra/idempotency.py —— 基于 Redis 的幂等去重(替换内存 set)

SET key value NX EX ttl：仅当 key 不存在时设成功。
第一次见→设成功→返回 False(应处理);重复→设失败→返回 True(应跳过)。
跨副本共享、带过期、重启不丢、原子无竞态。
"""
from redis.asyncio import Redis


async def seen_before(redis: Redis, key: str, ttl_seconds: int = 3600) -> bool:
    """True=之前已见过(应跳过)，False=第一次见(应处理)。"""
    was_set = await redis.set(f"idem:{key}", "1", nx=True, ex=ttl_seconds)
    return was_set is None     # 已存在(None)→见过→True



