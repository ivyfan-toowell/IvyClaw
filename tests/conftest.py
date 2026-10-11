"""离线测试默认值；真实服务凭据不会用于测试。"""
import os

# 单元测试的 Redis 均由夹具替代，HTTP 装饰器不得再连接外部 Redis。
os.environ["IVC_RATELIMIT_ENABLED"] = "false"

os.environ["IVC_API_KEY"] = "offline-test-placeholder"
os.environ["IVC_LANGSMITH_TRACING"] = "false"
