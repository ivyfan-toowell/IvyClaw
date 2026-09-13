"""gateway/limiter.py —— SlowAPI 限流器（按 tenant_id 分桶 + Redis 多副本共享）"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from infra.settings import get_settings



_s = get_settings()

def _tenant_key(request) -> str:
    """限流维度：把 API key 映射到租户,按 tenant_id 分桶(复用第 9 章映射)。"""
    api_key = request.headers.get("Gateway-API-Key")
    tenant = get_settings().gateway_api_keys.get(api_key) if api_key else None
    return f"tenant:{tenant}" if tenant else get_remote_address(request)


limiter = Limiter(
    key_func=_tenant_key,
    storage_uri=get_settings().redis_url,   # Redis：多副本共享计数
    default_limits=[],                      # 按路由单独设
    enabled=_s.ratelimit_enabled,      # 开关：false 时限流整体不生效
)