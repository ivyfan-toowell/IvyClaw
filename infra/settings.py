"""
infra/settings.py —— ShanYangClaw 的配置中枢

- 所有 API Key / Base URL / 连接串统一从这里取，不散落在业务代码里
- Pydantic Settings 做类型校验，缺失关键项时给清晰报错
- 字段前缀 SYC_（ShanYangClaw 缩写），避免与系统其他环境变量撞名
"""
import os
from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IVC_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 模型 =====
    model_name: str = "qwen-max"
    model_provider: str = "openai"
    api_key: SecretStr                    # 用 SecretStr，避免密钥被 print/log 泄露
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ===== 模型档位 =====
    model_tiers: dict[str, str] = {
        "strong": "qwen-max",  # 难任务：规划、写代码、审查
        "standard": "qwen-plus",  # 中等任务：测试
        "cheap": "qwen-turbo",  # 简单任务：读代码、总结
    }

    # ===== 连接弹性 =====
    max_retries: int = 12
    timeout: int = 60

    # ===== 持久化底座 =====
    postgres_url: str = "postgresql://user:password@localhost:5432/ivyclaw"
    redis_url: str = "redis://localhost:6379/0"

    # ===== 运行 =====
    log_level: str = "INFO"

    # MCP server 配置（默认空 = 不接任何 MCP）。
    # 实际项目里可从环境变量 JSON 或单独的 toml 读；这里给默认空字典，按需在代码/配置里填。
    mcp_servers: dict[str, dict] = {}

    # Postgres（第 8 章持久化 + 连接池）
    database_url: str = "postgresql://ivy:ivy@localhost:5432/ivyclaw"# 按第1章 compose 改
    pg_pool_min: int = 2
    pg_pool_max: int = 20

    # Redis（第 8 章备好，后半 arq/限流用）
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_max: int = 20

    # 飞书（第 9 章）—— .env 里写 IVC_FEISHU_*，pydantic-settings 自动映射到下面字段
    feishu_app_id: str = ""
    feishu_app_secret: SecretStr = SecretStr("")
    feishu_encrypt_key: str = ""           # 长连接可留空；Webhook 回调模式才用
    feishu_verification_token: str = ""    # 同上

    # 网关多租户（第 9 章，给 require_api_key / ch09_test_gateway / ch09_test_tenant 用）
    # 形如 {"key-tenant-a": "tenant-a", "key-tenant-b": "tenant-b"}
    gateway_api_keys: dict[str, str] = {
        "key-1": "<tenant-001>",
        "key-2": "<tenant-002>",
        "key-3": "<tenant-003>",
        "key-4": "<tenant-004>",
        "key-5": "<tenant-005>",
    }


    # ===== Daytona沙箱 ===== 还是不要放在这里统一管理
    # daytona_api_key: SecretStr
    # daytona_target: str = "us"

    # ===== 第 11 章：沙箱隔离 =====
    sandbox_provider: str = "docker"        # docker（自托管）/ daytona（第 6 章外部托管）
    sandbox_runtime: str = "runc"           # runc(加固容器) / runsc(gVisor) / kata(microVM)
    sandbox_image: str = "ivy-sandbox:latest"  # 3.3 会用 Dockerfile 构建这个镜像
    sandbox_workdir: str = "/home/agent"    # 容器内工作目录（tmpfs，可写）
    sandbox_mem_limit: str = "512m"
    sandbox_pids_limit: int = 256
    sandbox_cpus: str = "1.0"
    sandbox_pool_size: int = 4              # 沙箱池并发上限（第 5 节）

    # ===== 第 11 章：并发与限流 =====
    max_concurrent_llm: int = 8             # LLM 并发调用上限（第 6 节）

    # ===== LangSmith 可观测（.env 里用 SYC_LANGSMITH_*，由 env_prefix 映射到这里）=====
    langsmith_tracing: bool = True
    langsmith_api_key: SecretStr = SecretStr("")
    langsmith_project: str = "ivy-claw"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # infra/settings.py（Settings 类加）
    ratelimit_enabled: bool = True  # 压测时 .env 设 SYC_RATELIMIT_ENABLED=false 关掉



def _export_langsmith_env(s: "Settings") -> None:
    """把 LangSmith 变量写回 os.environ。

    关键：LangSmith 库只认系统环境变量，不读 Settings 对象——所以必须写回 os.environ。
    只在开启 tracing 时写，避免没配 key 时设一堆空变量。
    """
    if not s.langsmith_tracing:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = s.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = s.langsmith_endpoint


# ===== 模块级执行：import 这个模块时就把环境变量写好 =====
# 放模块级（不只在 get_settings 里）是为了保证：任何代码一旦 import infra.settings，
# LangSmith 变量就立刻进环境，且通常早于 langchain/langgraph 真正使用追踪。
_settings = Settings()
_export_langsmith_env(_settings)


@lru_cache
def get_settings() -> Settings:
    """全进程单例。业务代码统一通过它拿配置。"""
    return Settings()