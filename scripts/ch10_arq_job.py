"""scripts/ch10_arq_job.py —— 第 10 章方案二：arq 任务提交 + 轮询
三进程都要起：Redis、arq worker、uvicorn 服务。
运行：uv run python -m scripts.ch10_arq_job
"""
import asyncio
import httpx

BASE = "http://localhost:8000"


async def main():
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{BASE}/jobs", json={"text": "用一句话解释任务队列。", "user_id": "alice"})
        job_id = r.json()["job_id"]
        print("① 已提交，job_id =", job_id, "（服务秒级返回，执行在 worker 进程）")
        for i in range(60):
            await asyncio.sleep(2)
            data = (await client.get(f"{BASE}/jobs/{job_id}")).json()
            print(f"   第{i+1}次：status={data['status']}")
            if data["status"] == "complete":
                print("\n② 结果：", data.get("result", {}).get("reply", "")[:200])
                break


if __name__ == "__main__":
    asyncio.run(main())