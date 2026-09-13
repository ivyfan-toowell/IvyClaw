"""scripts/ch09_test_tenant.py —— 第 9 章：多租户隔离验证（调服务，正反两面）

先启动服务（确认 /docs 里有 /issues/secure）：uv run uvicorn api.app:app --reload --port 8000
需 settings.api_keys 配好至少两个租户的 key，例如：
    {
        "key-1": "<tenant-001>",
        "key-2": "<tenant-002>",
        "key-3": "<tenant-003>",
        "key-4": "<tenant-004>",
        "key-5": "<tenant-005>",
    }
运行：uv run python -m scripts.ch09_test_tenant
"""
import asyncio
import httpx

BASE = "http://localhost:8000"


async def main():
    from infra.settings import get_settings
    keys = list(get_settings().gateway_api_keys.keys())
    if len(keys) < 2:
        print("⚠️ 需要至少 2 个租户 key 才能演示隔离（在 settings.api_keys 配两个）")
        return
    key_a, key_b = keys[0], keys[1]
    passed = total = 0

    def check(name, cond, detail=""):
        nonlocal passed, total
        total += 1
        passed += 1 if cond else 0
        print(f"  {'✅' if cond else '❌'} {name} {detail}")

    async with httpx.AsyncClient(timeout=300) as client:
        # 租户A 告诉 DevMate 一个"暗号"（用某个 user_id / thread_id）
        await client.post(f"{BASE}/issues/secure", headers={"Gateway-API-Key": key_a},
            json={"issue": "记住暗号：蓝鲸。", "user_id": "same-user", "thread_id": "same-conv"})

        # —— 正面：同租户A、同会话追问 —— 应该【记得】（证明记忆本身是工作的）
        r_same = await client.post(f"{BASE}/issues/secure", headers={"Gateway-API-Key": key_a},
            json={"issue": "暗号是什么？", "user_id": "same-user", "thread_id": "same-conv"})
        reply_same = r_same.json().get("reply", "")
        check("同租户同会话 → 记得暗号", "蓝鲸" in reply_same, f"（回复:{reply_same[:40]}）")

        # —— 反面：换租户B、用【完全相同】的 user_id/thread_id 问 —— 应该【不知道】（隔离）
        r_other = await client.post(f"{BASE}/issues/secure", headers={"Gateway-API-Key": key_b},
            json={"issue": "暗号是什么？", "user_id": "same-user", "thread_id": "same-conv"})
        reply_other = r_other.json().get("reply", "")
        check("换租户同会话 → 不知道暗号（隔离）", "蓝鲸" not in reply_other, f"（回复:{reply_other[:40]}）")

    print(f"\n多租户隔离测试：{passed}/{total} 通过")
    if passed < total:
        print("❌ 检查 thread_id_for 是否纳入 tenant、secure 端点是否把 tenant 传进了 handle_message")


if __name__ == "__main__":
    asyncio.run(main())