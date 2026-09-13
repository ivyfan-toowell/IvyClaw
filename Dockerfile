FROM docker:cli AS docker-cli

FROM python:3.13-slim

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

# 如果服务器在国内，可以保留清华源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "scripts/start_web.sh"]