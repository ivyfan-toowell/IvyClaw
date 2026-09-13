"""
gateway/auth.py —— 网关鉴权（API Key 示例 + 多租户上下文）
用 FastAPI 依赖注入：在路由上声明 Depends(require_api_key)，
未带或错误的 key 直接 401，不进入业务。
"""
from fastapi import Header, HTTPException, status

from infra.settings import get_settings


async def require_api_key(gateway_api_key: str | None = Header(None)) -> str:
    """
    校验请求头 X-API-Key。返回它对应的租户标识（这里简化为 key 本身）。
    生产里：key → 租户的映射查数据库/配置；这里用 settings 里配的允许列表演示。
    """
    s = get_settings()
    allowed = s.gateway_api_keys  # dict: {gateway_api_key: tenant_id}
    if not gateway_api_key or gateway_api_key not in allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
        )
    return allowed[gateway_api_key]   # 返回租户 id，供下游使用