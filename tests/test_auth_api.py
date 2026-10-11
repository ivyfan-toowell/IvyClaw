"""Web 身份、CSRF、用户隔离和任务归属测试。"""
from types import SimpleNamespace
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.auth import router as auth_router
from api.routes.jobs import router as jobs_router
from api.routes.issues import router as issues_router
from api.schemas import AuthUser
from channels.webhook import router as webhook_router
from gateway.users import hash_password, session_key, verify_password
from psycopg.errors import UniqueViolation


def auth_client() -> tuple[TestClient, SimpleNamespace]:
    """创建不依赖外部服务的认证路由测试客户端。"""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(issues_router)
    app.include_router(webhook_router)
    redis = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock(), delete=AsyncMock(),
                            incr=AsyncMock(return_value=1), expire=AsyncMock())
    app.state.redis = redis
    app.state.arq_redis = redis
    app.state.checkpointer = object()
    app.state.store = None
    return TestClient(app), redis


def test_password_hashes_use_salt_and_verify() -> None:
    """同密码不同盐，错误密码不能通过。"""
    password = "correct-horse-123"
    one, two = hash_password(password), hash_password(password)
    assert one != two and password not in one
    assert verify_password(password, one)
    assert not verify_password("wrong-password", one)
    assert not verify_password(password, "broken")


@pytest.mark.parametrize("path,body", [("/jobs", {"text": "task"}), ("/issues", {"issue": "task"}),
                                       ("/webhook/generic", {"text": "task", "source": "victim"})])
def test_agent_endpoints_require_login(path, body) -> None:
    """客户端伪造 user_id/source 无法匿名执行任务。"""
    client, _ = auth_client()
    assert client.post(path, json=body).status_code == 401


def test_write_requires_csrf_and_job_payload_uses_session_identity(monkeypatch) -> None:
    """账户与请求身份冲突时，以 Cookie 会话为准。"""
    from api.routes import jobs
    client, redis = auth_client()
    user = AuthUser(user_id="alice", username="alice", csrf_token="csrf")
    redis.get.return_value = user.model_dump_json()
    client.cookies.set("ivyclaw_session", "token")
    payload = {"text": "task", "user_id": "victim", "channel": "feishu", "conversation_id": "conversation"}
    assert client.post("/jobs", json=payload).status_code == 403
    enqueue = AsyncMock(return_value="job")
    monkeypatch.setattr(jobs, "enqueue_issue", enqueue)
    response = client.post("/jobs", json=payload, headers={"X-CSRF-Token": "csrf"})
    assert response.status_code == 200
    sent = enqueue.await_args.args[1]
    assert sent["user_id"] == "alice" and sent["channel"] == "web"


def test_job_result_is_private(monkeypatch) -> None:
    """知道他人的 job_id 也不能查询结果。"""
    from api.routes import jobs
    client, redis = auth_client()
    user = AuthUser(user_id="alice", username="alice", csrf_token="csrf")
    redis.get.side_effect = [user.model_dump_json(), b"bob"]
    client.cookies.set("ivyclaw_session", "token")
    get_result = AsyncMock()
    monkeypatch.setattr(jobs, "get_job_result", get_result)
    assert client.get("/jobs/secret").status_code == 404
    get_result.assert_not_awaited()


def test_logout_revokes_session() -> None:
    """退出使服务端会话失效。"""
    client, redis = auth_client()
    user = AuthUser(user_id="alice", username="alice", csrf_token="csrf")
    redis.get.return_value = user.model_dump_json()
    client.cookies.set("ivyclaw_session", "token")
    response = client.post("/auth/logout", headers={"X-CSRF-Token": "csrf"})
    assert response.status_code == 204
    redis.delete.assert_awaited_once_with(session_key("token"))


def test_cross_origin_login_is_rejected() -> None:
    """登录种植攻击在数据库查询前拒绝。"""
    client, _ = auth_client()
    response = client.post("/auth/login", json={"username": "alice", "password": "long-password-123"},
                           headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403


@pytest.mark.parametrize("text", ["", " \n\t ", "x" * 100001], ids=["empty", "whitespace", "over-limit"])
def test_invalid_job_text_rejected_before_enqueue(text: str, monkeypatch) -> None:
    """空白与超限文本在队列入口拒绝，不能消耗模型资源。"""
    from api.routes import jobs
    client, redis = auth_client()
    redis.get.return_value = AuthUser(user_id="alice", username="alice", csrf_token="csrf").model_dump_json()
    client.cookies.set("ivyclaw_session", "token")
    enqueue = AsyncMock()
    monkeypatch.setattr(jobs, "enqueue_issue", enqueue)
    assert client.post("/jobs", json={"text": text}, headers={"X-CSRF-Token": "csrf"}).status_code == 422
    enqueue.assert_not_awaited()


@pytest.mark.parametrize("password", ["Abc123", "correct-horse-123", "x" * 128],
                         ids=["minimum-six", "ordinary", "maximum-128"])
def test_register_login_rotation_and_logout(monkeypatch, password: str) -> None:
    """实际认证函数验证密码、设置安全 Cookie，轮换并撤销会话。"""
    client, redis = auth_client()
    users = {}
    sessions = {}
    redis.get.side_effect = lambda key: sessions.get(key)
    redis.set.side_effect = lambda key, value, **kwargs: sessions.__setitem__(key, value)
    redis.delete.side_effect = lambda key: sessions.pop(key, None)

    async def execute(sql, args):
        if sql.startswith("INSERT"):
            user_id, username, encoded = args
            if username in users:
                raise UniqueViolation("duplicate")
            users[username] = {"user_id": user_id, "password_hash": encoded}
            return None
        return SimpleNamespace(fetchone=AsyncMock(return_value=users.get(args[0])))

    @asynccontextmanager
    async def connection():
        yield SimpleNamespace(execute=execute)

    client.app.state.pg_pool = SimpleNamespace(connection=connection)
    credentials = {"username": "Alice", "password": password}
    response = client.post("/auth/register", json=credentials)
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
    assert response.json()["username"] == "alice"
    original_key = next(iter(sessions))
    assert credentials["password"] not in users["alice"]["password_hash"]
    assert client.get("/auth/me").json()["userId"] == response.json()["userId"]
    assert client.post("/auth/register", json=credentials).status_code == 409
    invalid = {**credentials, "password": "incorrect-password"}
    assert client.post("/auth/login", json=invalid).status_code == 401
    login = client.post("/auth/login", json=credentials)
    assert login.status_code == 200 and original_key not in sessions
    assert client.post("/auth/logout", headers={"X-CSRF-Token": login.json()["csrfToken"]}).status_code == 204
    assert not sessions and client.get("/auth/me").status_code == 401


@pytest.mark.parametrize("path", ["/auth/register", "/auth/login"])
@pytest.mark.parametrize("password", ["", "12345", "x" * 129], ids=["empty", "five", "over-limit"])
def test_invalid_password_lengths_rejected_before_authentication(path: str, password: str) -> None:
    """注册和登录统一拒绝不足 6 位及超限密码，且不触发数据库或哈希。"""
    client, redis = auth_client()
    response = client.post(path, json={"username": "alice", "password": password})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    redis.incr.assert_not_awaited()


def test_login_attempt_limit_precedes_database() -> None:
    """限流不继续进行昂贵哈希或数据库验证。"""
    client, redis = auth_client()
    redis.incr.return_value = 21
    response = client.post("/auth/login", json={"username": "alice", "password": "long-password-123"})
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_memory_api_and_conversations_are_owned_by_session(monkeypatch) -> None:
    """账户偏好和历史接口不允许访问另一用户的会话。"""
    from langgraph.store.memory import InMemoryStore
    from api.routes import memory as routes
    from app.memory import MemoryService
    from app.schemas import MemoryExtraction, PreferencePatch
    client, redis = auth_client()
    client.app.include_router(routes.router)
    store = InMemoryStore()
    service = MemoryService(store, "alice")
    await service.update_preferences(PreferencePatch(response_style="detailed"))
    await service.record_turn("shared", "private task", "private reply", MemoryExtraction())
    monkeypatch.setattr(routes, "user_memory", lambda request, user: MemoryService(store, user.user_id))
    client.cookies.set("ivyclaw_session", "token")
    redis.get.return_value = AuthUser(user_id="alice", username="alice", csrf_token="csrf").model_dump_json()
    assert client.get("/me/preferences").json()["responseStyle"] == "detailed"
    assert client.get("/conversations/shared").json()["turns"][0]["reply"] == "private reply"
    index = client.get("/conversations").json()[0]
    assert index["conversationId"] == "shared" and "turns" not in index
    redis.get.return_value = AuthUser(user_id="bob", username="bob", csrf_token="csrf").model_dump_json()
    assert client.get("/conversations/shared").status_code == 404
    assert client.get("/me/memory").json()["semantic"] == []
    assert client.get("/me/preferences").json()["responseStyle"] == "concise"
    assert client.patch("/me/preferences", json={"responseStyle": "detailed"}).status_code == 403
    assert client.patch("/me/preferences", json={"responseStyle": "detailed"}, headers={"X-CSRF-Token": "csrf"}).status_code == 200


@pytest.mark.asyncio
async def test_account_schema_lock_is_transaction_scoped() -> None:
    """首建表之前获取事务锁，并在提交时释放，避免多进程首次启动冲突。"""
    from gateway.users import setup_users
    calls = []

    @asynccontextmanager
    async def transaction():
        calls.append("begin")
        yield
        calls.append("commit")

    async def execute(sql, args=None):
        calls.append(sql)

    @asynccontextmanager
    async def connection():
        yield SimpleNamespace(transaction=transaction, execute=execute)

    await setup_users(SimpleNamespace(connection=connection))
    assert calls[0] == "begin" and calls[-1] == "commit"
    assert "pg_advisory_xact_lock" in calls[1]
    assert calls[2].startswith("CREATE TABLE IF NOT EXISTS ivyclaw_users")
