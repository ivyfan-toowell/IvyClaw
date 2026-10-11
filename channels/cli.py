"""channels/cli.py —— CLI 渠道：终端里跟 DevMate 对话

直接调本机服务的 HTTP 接口（需先启动 api.app）。
用同一个 --session 多次调用即可续聊（thread_id 由 (cli, session) 稳定派生）。

运行：uv run python -m channels.cli --session mywork "帮我看下订单服务的定价逻辑"
"""
import argparse
import asyncio
import getpass

import httpx

BASE = "http://localhost:8000"


async def ask(session: str, text: str, username: str | None = None) -> None:
    """使用 Web 账户登录并提交后台任务，密码不进入命令行参数。"""
    username = username or input("用户名：").strip()
    password = getpass.getpass("密码：")
    async with httpx.AsyncClient(timeout=30) as client:
        login = await client.post(f"{BASE}/auth/login", json={"username": username, "password": password})
        login.raise_for_status()
        user = login.json()
        response = await client.post(f"{BASE}/jobs", json={"text": text, "conversation_id": f"cli:{session}"},
                                     headers={"X-CSRF-Token": user["csrfToken"]})
        response.raise_for_status()
        job_id = response.json()["job_id"]
        print("任务已入队：", job_id)
        while True:
            response = await client.get(f"{BASE}/jobs/{job_id}")
            response.raise_for_status()
            result = response.json()
            if result.get("error"):
                raise RuntimeError(result["error"])
            if result["status"] == "complete":
                print("\nDevMate:", result["result"]["reply"])
                return
            if result["status"] == "not_found":
                raise RuntimeError("任务结果不存在或已过期")
            await asyncio.sleep(1)


def main() -> None:
    """解析会话与登录账户参数。"""
    p = argparse.ArgumentParser(description="DevMate CLI")
    p.add_argument("--session", default="default", help="会话名（同名续聊）")
    p.add_argument("--username", help="已有 Web 账户用户名；密码交互输入")
    p.add_argument("text", help="要对 DevMate 说的话")
    args = p.parse_args()
    asyncio.run(ask(args.session, args.text, args.username))


if __name__ == "__main__":
    main()
