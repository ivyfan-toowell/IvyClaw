"""verify_env.py —— 启动期自检（异步版，与全课异步基调一致）"""
import asyncio
import sys

import psycopg
import redis.asyncio as aioredis
from infra.settings import get_settings


async def main():
    s = get_settings()
    print("✅ 配置加载成功：")
    print(f"   model    = {s.model_provider}:{s.model_name}")
    print(f"   api_key  = {s.api_key}")              # SecretStr 自动脱敏成 **********
    print("   postgres = configured")
    print("   redis    = configured")

    # Postgres（异步连接）
    aconn = await psycopg.AsyncConnection.connect(s.postgres_url)
    async with aconn:
        cur = await aconn.execute("SELECT version();")
        ver = (await cur.fetchone())[0]
        print(f"✅ Postgres 连通：{ver[:40]}...")

    # Redis（异步连接）
    r = aioredis.from_url(s.redis_url)
    pong = await r.ping()
    await r.aclose()
    print(f"✅ Redis 连通：ping = {pong}")


if __name__ == "__main__":
    # 针对 Windows 系统的特殊处理：将事件循环策略修改为 SelectorEventLoop
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())