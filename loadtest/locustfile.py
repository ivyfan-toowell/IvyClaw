"""loadtest/locustfile.py —— DevMate 服务压测（小规模教学版）

依赖：uv add locust
Windows 注意：跑前先 $env:PYTHONUTF8="1"，否则 locust 读 pyproject.toml 可能报 GBK 解码错。
Web UI： uv run locust -f loadtest/locustfile.py --host http://服务器IP:18700
然后浏览器开 http://localhost:8089 设并发开压。
"""


from locust import HttpUser, task, between


class LightUser(HttpUser):
    """压轻端点测纯框架吞吐——不触发 agent、不烧钱、不撞限流。"""
    wait_time = between(1, 2)

    @task
    def health(self):
        self.client.get("/readyz")


class JobUser(HttpUser):
    """压 /jobs 端到端——会真跑 agent、烧钱，必须先关限流（3.2），只做小规模。"""
    wait_time = between(2, 5)

    @task
    def submit_job(self):
        self.client.post("/jobs", json={"text": "用一句话解释幂等性", "user_id": "lt"},
                         headers={"Gateway-API-Key": "key-1"})