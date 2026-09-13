"""
scripts/ch09_test_gateway.py —— 第 9 章：网关鉴权测试（TestClient，多用例）

用 FastAPI TestClient 在进程内验证 require_api_key 的多种情况，不依赖真实服务/网络。
运行：uv run python -m scripts.ch09_test_gateway

注意：本测试需要 settings.api_keys 里配 key。多租户用例建议配两个，例如：
    {"key-a": "tenant-a", "key-b": "tenant-b"}
"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from gateway.auth import require_api_key
from infra.settings import get_settings

_app = FastAPI()


@_app.get("/protected")
async def protected(tenant: str = Depends(require_api_key)):
    return {"tenant": tenant}


def main():
    client = TestClient(_app)
    keys = list(get_settings().gateway_api_keys.items())   # [(key, tenant), ...]
    passed = total = 0

    def check(name, cond):
        nonlocal passed, total
        total += 1
        passed += 1 if cond else 0
        print(f"  {'✅' if cond else '❌'} {name}")

    # —— 无效凭证：都应 401 ——
    check("不带 key → 401", client.get("/protected").status_code == 401)
    check("空 key → 401", client.get("/protected", headers={"Gateway-API-Key": ""}).status_code == 401)
    check("错误 key → 401",
          client.get("/protected", headers={"Gateway-API-Key": "wrong-key"}).status_code == 401)
    # key 带前后空格：当前实现是精确匹配，应被拒（提醒：要不要 strip 是设计决定）
    if keys:
        k0 = keys[0][0]
        check("带空格的正确 key → 401（精确匹配）",
              client.get("/protected", headers={"Gateway-API-Key": f" {k0} "}).status_code == 401)

    # —— 有效凭证：每个租户的 key 都应放行、且映射到正确的 tenant ——
    if keys:
        for k, tenant in keys:
            r = client.get("/protected", headers={"Gateway-API-Key": k})
            ok = r.status_code == 200 and r.json().get("tenant") == tenant
            check(f"正确 key（{tenant}）→ 200 且映射对", ok)
    else:
        print("  ⚠️ settings.gateway_api_keys 为空，跳过有效 key 用例——请先配 key")

    print(f"\n网关鉴权测试：{passed}/{total} 通过")


if __name__ == "__main__":
    main()