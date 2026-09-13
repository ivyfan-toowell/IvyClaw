"""scripts/ch09_channels.py —— 验证 Webhook 渠道 + 多轮会话

先启动服务：uv run uvicorn api.app:app --port 8000
再运行：uv run python -m scripts.ch09_channels
"""
import asyncio
import httpx

BASE = "http://localhost:8000"


async def main():
    async with httpx.AsyncClient(timeout=300) as client:
        conv = "demo-conv-001"
        # 第一轮：告诉它一个事实（同一个 conversation_id）
        await client.post(f"{BASE}/webhook/generic", json={
            "text": "你好，我的猫咪名字叫糯米，她出生于去年的10月27日。",
            "source": "test", "conversation_id": conv,
        })
        # 第二轮：同 conversation_id 追问 —— 它应该「记得」（同会话续聊）
        r2 = await client.post(f"{BASE}/webhook/generic", json={
            "text": "我的猫咪叫什么名字？出生于什么时间？", "source": "test", "conversation_id": conv,
        })
        print("② 同会话（应记得）：", r2.json().get("reply", "")[:150])

        # 第三轮：换一个 conversation_id 问同样的话 —— 它应该「不记得」（不同会话隔离）
        r3 = await client.post(f"{BASE}/webhook/generic", json={
            "text": "我的猫咪叫什么名字？出生于什么时间？", "source": "test", "conversation_id": "demo-conv-002",
        })
        print("③ 新会话（应不记得）：", r3.json().get("reply", "")[:150])


if __name__ == "__main__":
    asyncio.run(main())