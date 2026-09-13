"""scripts/ch08_call_service.py —— 第 8 章：调 DevMate 服务自测（含续聊）

先启动服务：uv run uvicorn api.app:app --port 8000
再运行本脚本：uv run python -m scripts.ch08_call_service
"""
import asyncio
import httpx

BASE = "http://localhost:8000"


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        # 健康检查
        r = await client.get(f"{BASE}/readyz")
        print("readyz:", r.status_code, r.json())

        # ① 第一次提交 Issue（不带 thread_id）
        r1 = await client.post(f"{BASE}/issues", json={
            "issue": "用一句话说明订单服务里金额为什么要用 Decimal 而不是 float。",
            "user_id": "alice",
        })
        d1 = r1.json()
        print("\n① 首次回复：", d1["reply"][:200])
        tid = d1["thread_id"]
        print("   thread_id =", tid)

        # ② 带上同一个 thread_id 续聊（agent 应记得上一轮在聊 Decimal）
        r2 = await client.post(f"{BASE}/issues", json={
            "issue": "那请给我一个对应的代码示例。",
            "user_id": "alice",
            "thread_id": tid,        # ← 关键：带上它，续上同一对话
        })
        print("\n② 续聊回复：", r2.json()["reply"][:300])


if __name__ == "__main__":
    asyncio.run(main())