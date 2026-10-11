# sandbox/Dockerfile —— 加固容器用的沙箱镜像（预装 pytest 等依赖）
FROM ghcr.io/astral-sh/uv:0.11.27 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /uvx /usr/local/bin/

# 预装测试/常用依赖，避免容器内断网现装
WORKDIR /opt/ivyclaw
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 UV_HTTP_RETRIES=5 UV_CONCURRENT_DOWNLOADS=4 UV_LINK_MODE=copy \
    uv sync --frozen --no-install-project
ENV PATH="/opt/ivyclaw/.venv/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT="/opt/ivyclaw/.venv"
ENV UV_NO_SYNC="true"
# 测试默认只使用占位凭据，宿主机的模型密钥不会进入沙箱。
ENV IVC_API_KEY="sandbox-test-placeholder"
ENV IVC_LANGSMITH_TRACING="false"

# 创建非 root 用户（uid 1000，与 docker run --user 1000:1000 对齐）
RUN useradd -m -u 1000 agent

# 工作目录 + Python 缓存目录都放在工作目录下（确保在可写 tmpfs 范围内）
ENV HOME=/home/agent
ENV PYTHONPYCACHEPREFIX=/home/agent/.pycache
ENV PYTEST_ADDOPTS="-p no:cacheprovider"

WORKDIR /home/agent
USER 1000:1000
