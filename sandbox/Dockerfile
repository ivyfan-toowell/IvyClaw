# sandbox/Dockerfile —— 加固容器用的沙箱镜像（预装 pytest 等依赖）
FROM python:3.13-slim

# 预装测试/常用依赖，避免容器内断网现装
RUN pip install --no-cache-dir pytest pytest-asyncio

# 创建非 root 用户（uid 1000，与 docker run --user 1000:1000 对齐）
RUN useradd -m -u 1000 agent

# 工作目录 + Python 缓存目录都放在工作目录下（确保在可写 tmpfs 范围内）
ENV HOME=/home/agent
ENV PYTHONPYCACHEPREFIX=/home/agent/.pycache
ENV PYTEST_ADDOPTS="-p no:cacheprovider"

WORKDIR /home/agent
USER 1000:1000