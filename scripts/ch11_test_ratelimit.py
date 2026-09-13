"""scripts/ch11_test_ratelimit.py —— 第 11 章：限流验证
先启动服务：uv run uvicorn api.app:app --reload --port 8000(jobs 端点加了 @limiter.limit、Redis 在跑)
需 settings.api_keys 里配 key。运行：uv run python -m scripts.ch11_test_ratelimit
"""
import asyncio
import httpx

BASE = "http://localhost:8000"


async def main():
    headers = {"Gateway-API-Key": "key-1"}    # 用 settings.api_keys 里配的 key
    ok = limited = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(13):             # 设了 10/minute,连发 13 次
            r = await client.post(f"{BASE}/jobs", headers=headers,
                                   json={"text": "ping", "user_id": "u"})
            if r.status_code == 200:
                ok += 1
            elif r.status_code == 429:
                limited += 1
            print(f"  第{i+1}次：{r.status_code}")
    print(f"\n通过 {ok}、被限流(429) {limited}",
          "✅ 限流生效" if limited > 0 else "❌ 没触发(检查装饰器顺序/request 参数)")


if __name__ == "__main__":
    asyncio.run(main())