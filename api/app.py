"""api/app.py —— FastAPI 入口 + lifespan（建池/持久化/挂资源）

工程化核心：
- 在 lifespan 建一个 AsyncConnectionPool，同时构造 AsyncPostgresSaver + AsyncPostgresStore；
- setup() 建表（首次）；把 checkpointer/store/redis 挂到 app.state 供全局复用；
- 关闭时统一释放——资源生命周期完全归服务所有，绝不在请求里临时建连。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from infra.db import build_pg_pool
from infra.redis import build_redis
from infra.logging import get_logger
from profiles.qwen_profile import register_all_profiles
from api.schemas import HealthResponse
from api.routes.issues import router as issues_router#在下面有
from channels.webhook import router as webhook_router
from api.routes.jobs import router as jobs_router    # ← 新增：import 路由
from tasks.queue import get_arq_redis

from fastapi.middleware.cors import CORSMiddleware

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from gateway.limiter import limiter

import os
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from obs.metrics import PrometheusMiddleware
from obs.metrics import RATELIMIT_REJECTED


logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ① 注册 Harness Profile（第 7 章）——在任何 agent 构建前
    register_all_profiles()

    # ② 建并打开 Postgres 连接池（一个池，喂 saver + store）
    pool = build_pg_pool()
    await pool.open()
    logger.info("🔗  Postgres 连接池已打开")

    # ③ 用同一个池构造异步 saver / store，并 setup（首次建表）
    checkpointer = AsyncPostgresSaver(pool)
    store = AsyncPostgresStore(pool)
    await checkpointer.setup()
    await store.setup()
    logger.info("🔗  AsyncPostgresSaver / AsyncPostgresStore 已 setup")

    # ④ Redis 池
    redis = build_redis()



    # ⑤ 挂到 app.state，供所有请求复用
    app.state.pg_pool = pool
    app.state.checkpointer = checkpointer
    app.state.store = store
    app.state.redis = redis
    app.state.limiter = limiter

    arq_redis = await get_arq_redis()
    app.state.arq_redis = arq_redis

    try:
        yield                      # —— 服务运行中 ——
    finally:
        # ⑥ 关闭时统一释放
        await redis.aclose()
        await pool.close()
        await arq_redis.close()
        logger.info("🔗  连接池已释放")




def rate_limit_handler(request, exc):
    RATELIMIT_REJECTED.labels("unknown").inc()
    return _rate_limit_exceeded_handler(request, exc)


app = FastAPI(title="IvyClaw DevMate API", lifespan=lifespan)
app.include_router(issues_router)
app.include_router(webhook_router)
app.include_router(jobs_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 开发期放开；生产应收紧到你的前端域名
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.add_middleware(PrometheusMiddleware)


@app.get("/", include_in_schema=False)
async def web_home():
    return FileResponse("web/index.html")



# 统一异常处理：不把内部堆栈暴露给客户端
@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception):
    logger.exception("未处理异常：{}", exc)
    return JSONResponse(status_code=500, content={"detail": "内部错误，请稍后重试"})


# 健康检查：liveness（纯探活）
@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    return HealthResponse(status="ok")


# 健康检查：readiness（依赖就绪才 OK）
@app.get("/readyz", response_model=HealthResponse)
async def readyz(request: Request):
    pool = getattr(request.app.state, "pg_pool", None)
    if pool is None:
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": "pool 未就绪"})
    return HealthResponse(status="ready")


@app.get("/metrics")                              # 普通路由，避开 app.mount 的 307
async def metrics():
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        # 生产多进程（Gunicorn 多 worker）：聚合所有 worker
        from prometheus_client import CollectorRegistry, multiprocess
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest()                  # 本地单进程：默认全局 registry
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)