"""scripts/ch11_test_idempotency.py —— 第 11 章：Redis 幂等验证(需 Redis 在跑)
运行：uv run python -m scripts.ch11_test_idempotency
"""
import asyncio
from redis.asyncio import Redis
from infra.settings import get_settings
from infra.idempotency import seen_before


async def main():
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    key = "test-event-12345"
    await redis.delete(f"idem:{key}")
    first = await seen_before(redis, key)
    second = await seen_before(redis, key)
    print(f"  第一次：seen={first}(期望 False=应处理)", "✅" if first is False else "❌")
    print(f"  第二次：seen={second}(期望 True=应跳过)", "✅" if second is True else "❌")
    print("→ 同一事件只在第一次被处理,之后跳过;且存在 Redis 里、跨副本共享")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())