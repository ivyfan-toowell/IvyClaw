"""obs/metrics.py —— Prometheus 指标（HTTP 层 RED + Agent 层）

HTTP 层（RED 方法）：
- http_requests_total      Counter   总请求数 → QPS、错误率
- http_request_duration    Histogram 请求耗时 → P50/P99
- http_requests_in_flight  Gauge     在飞请求数 → 瞬时压力
"""
import time

from prometheus_client import Counter, Histogram, Gauge
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_COUNT = Counter(
    "http_requests_total", "HTTP 请求总数", ["method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP 请求耗时（秒）", ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
IN_FLIGHT = Gauge(
    "http_requests_in_flight", "当前正在处理的请求数",
    multiprocess_mode="livesum",
)


def _normalize_path(request: Request) -> str:
    """路径归一化（/jobs/abc → /jobs/{job_id}），防标签基数爆炸。"""
    route = request.scope.get("route")
    if route and getattr(route, "path", None):
        return route.path
    return request.url.path


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = _normalize_path(request)
        method = request.method
        IN_FLIGHT.inc()
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            IN_FLIGHT.dec()
            REQUEST_COUNT.labels(method, path, str(status)).inc()
            REQUEST_DURATION.labels(method, path).observe(elapsed)



# obs/metrics.py（在 HTTP 指标后追加）

# ===== 成本类（LLM 服务特有，企业最该盯的之一）=====
AGENT_LLM_TOKENS = Counter(
    "agent_llm_tokens_total", "LLM token 消耗总量",
    ["tier", "direction"],          # tier: strong/standard/cheap; direction: input/output
)
AGENT_LLM_COST = Counter(
    "agent_llm_cost_yuan_total", "LLM 调用成本（元）", ["tier"],
)

# ===== 延迟/错误类（Agent 内部，HTTP 层看不到）=====
AGENT_LLM_DURATION = Histogram(
    "agent_llm_call_duration_seconds", "单次模型调用耗时（秒）", ["tier"],
    buckets=(0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0),
)
AGENT_LLM_CALLS = Counter(
    "agent_llm_calls_total", "模型调用次数（按结果）", ["tier", "status"],  # status: ok/error
)
AGENT_TOOL_CALLS = Counter(
    "agent_tool_calls_total", "工具调用次数", ["tool", "status"],
)
AGENT_TOOL_DURATION = Histogram(
    "agent_tool_duration_seconds", "工具调用耗时（秒）", ["tool"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 60.0),
)

# ===== 弹性类 =====
AGENT_FALLBACK = Counter(
    "agent_fallback_total", "模型 fallback 触发次数", ["from_tier", "to_tier"],
)
RATELIMIT_REJECTED = Counter(
    "ratelimit_rejected_total", "被限流拒绝（429）次数", ["tenant"],
)
IDEMPOTENCY_HITS = Counter(
    "idempotency_hits_total", "幂等命中（重复事件被挡）次数",
)

# ===== 任务/队列/沙箱类（饱和度，主要在 worker 进程产生）=====
AGENT_TASK_DURATION = Histogram(
    "agent_task_duration_seconds", "一个 Issue 端到端执行耗时（秒）",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600),
)
AGENT_QUEUE_WAIT = Histogram(
    "agent_queue_wait_seconds", "任务入队到开始处理的等待（秒）",
    buckets=(0.1, 0.5, 1, 5, 15, 30, 60, 120),
)
AGENT_QUEUE_LENGTH = Gauge("agent_queue_length", "当前队列中待处理任务数")
SANDBOX_CREATE_DURATION = Histogram(
    "sandbox_create_duration_seconds", "沙箱创建（冷启动）耗时（秒）",
    buckets=(0.5, 1, 2, 5, 10, 30, 60),
)
SANDBOX_ACTIVE = Gauge("sandbox_active", "当前活跃沙箱数")

# 单价表（元 / 1K token），按你的实际计费填——把 token 换算成钱
# 真实企业里这张表通常从配置中心/计费服务动态拉，避免改价改代码
TOKEN_PRICE_PER_1K = {
    "strong":   {"input": 0.0024, "output": 0.0096},   # 示例：qwen-max
    "standard": {"input": 0.0008, "output": 0.0020},   # 示例：qwen-plus
    "cheap":    {"input": 0.0003, "output": 0.0006},   # 示例：qwen-turbo
}


def record_llm_cost(tier: str, input_tokens: int, output_tokens: int) -> None:
    """记录 token 用量并换算成钱。供 CostMeterMiddleware 调用。"""
    AGENT_LLM_TOKENS.labels(tier, "input").inc(input_tokens)
    AGENT_LLM_TOKENS.labels(tier, "output").inc(output_tokens)
    price = TOKEN_PRICE_PER_1K.get(tier, TOKEN_PRICE_PER_1K["standard"])
    cost = input_tokens / 1000 * price["input"] + output_tokens / 1000 * price["output"]
    AGENT_LLM_COST.labels(tier).inc(cost)

