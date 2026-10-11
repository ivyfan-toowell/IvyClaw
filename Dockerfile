FROM docker:cli AS docker-cli
FROM ghcr.io/astral-sh/uv:0.11.27 AS uv

FROM python:3.13-slim

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 UV_HTTP_RETRIES=5 UV_CONCURRENT_DOWNLOADS=4 UV_LINK_MODE=copy \
    uv sync --frozen --no-dev --extra deploy --extra serving --extra obs
ENV PATH="/app/.venv/bin:$PATH"

COPY . .

CMD ["bash", "scripts/start_web.sh"]
