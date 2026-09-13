"""channels/cli.py —— CLI 渠道：终端里跟 DevMate 对话

直接调本机服务的 HTTP 接口（需先启动 api.app）。
用同一个 --session 多次调用即可续聊（thread_id 由 (cli, session) 稳定派生）。

运行：uv run python -m channels.cli --session mywork "帮我看下订单服务的定价逻辑"
"""
import argparse
import asyncio

import httpx

BASE = "http://localhost:8000"


async def ask(session: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=300) as client:
        # 走通用 webhook 的 generic 入口（conversation_id=session 实现 CLI 续聊）
        r = await client.post(f"{BASE}/webhook/generic", json={
            "text": text,
            "source": "cli",
            "conversation_id": f"cli:{session}",
        })
        data = r.json()
        print("\nDevMate:", data.get("reply", data))


def main():
    p = argparse.ArgumentParser(description="DevMate CLI")
    p.add_argument("--session", default="default", help="会话名（同名续聊）")
    p.add_argument("text", help="要对 DevMate 说的话")
    args = p.parse_args()
    asyncio.run(ask(args.session, args.text))


if __name__ == "__main__":
    main()