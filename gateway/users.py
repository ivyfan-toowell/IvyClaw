"""Postgres 账户、scrypt 密码和 Redis 中可撤销的 Cookie 会话。"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request, Response
from psycopg.errors import UniqueViolation

from api.schemas import AuthUser, Credentials
from infra.settings import get_settings

COOKIE_NAME = "ivyclaw_session"


def hash_password(password: str, salt: str | None = None) -> str:
    """用独立盐和 scrypt 导出密码验证值。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"{salt}:{digest}"


def verify_password(password: str, encoded: str) -> bool:
    """常量时间比较密码派生结果。"""
    try:
        salt, _ = encoded.split(":", 1)
        return hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


async def setup_users(pool: Any) -> None:
    """串行创建账户表，避免多个 Gunicorn worker 同时首次建表。"""
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (731946821,))
            await conn.execute("""CREATE TABLE IF NOT EXISTS ivyclaw_users (
                user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")


async def authenticate(request: Request, credentials: Credentials, register: bool) -> AuthUser:
    """注册或验证密码；失败返回通用信息且限制尝试频率。"""
    username = credentials.username.lower()
    redis = request.app.state.redis
    ip = request.client.host if request.client else "unknown"
    rate_key = "auth-attempts:" + hashlib.sha256(ip.encode()).hexdigest()
    attempts = await redis.incr(rate_key)
    if attempts == 1:
        await redis.expire(rate_key, 300)
    if attempts > 20:
        raise HTTPException(429, "尝试过于频繁，请稍后再试")
    async with request.app.state.pg_pool.connection() as conn:
        if register:
            user_id = uuid4().hex
            encoded = await asyncio.to_thread(hash_password, credentials.password)
            try:
                await conn.execute(
                    "INSERT INTO ivyclaw_users (user_id, username, password_hash) VALUES (%s, %s, %s)",
                    (user_id, username, encoded),
                )
            except UniqueViolation as exc:
                raise HTTPException(409, "用户名不可用") from exc
        else:
            cursor = await conn.execute("SELECT user_id, password_hash FROM ivyclaw_users WHERE username = %s", (username,))
            row = await cursor.fetchone()
            # 不存在的用户也执行哈希，减少用户名枚举的时间差。
            encoded = row["password_hash"] if row else "0" * 32 + ":" + "0" * 128
            valid = await asyncio.to_thread(verify_password, credentials.password, encoded)
            if not row or not valid:
                raise HTTPException(401, "用户名或密码错误")
            user_id = row["user_id"]
    return AuthUser(user_id=user_id, username=username, csrf_token=secrets.token_urlsafe(32))


def session_key(token: str) -> str:
    """Redis 只保存会话令牌哈希对应的记录。"""
    return "session:" + hashlib.sha256(token.encode()).hexdigest()


async def create_session(request: Request, response: Response, user: AuthUser) -> None:
    """轮换旧会话并设置 HttpOnly、SameSite Cookie。"""
    settings = get_settings()
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        await request.app.state.redis.delete(session_key(old_token))
    token = secrets.token_urlsafe(48)
    await request.app.state.redis.set(session_key(token), user.model_dump_json(), ex=settings.session_ttl_seconds)
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=settings.session_cookie_secure,
                        samesite="lax", max_age=settings.session_ttl_seconds, path="/")
    response.headers["Cache-Control"] = "no-store"


async def require_user(request: Request) -> AuthUser:
    """获取服务端身份；写请求还必须通过 CSRF 检查。"""
    token = request.cookies.get(COOKIE_NAME)
    raw = await request.app.state.redis.get(session_key(token)) if token else None
    if not raw:
        raise HTTPException(401, "请先登录")
    user = AuthUser.model_validate_json(raw)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(csrf, user.csrf_token):
            raise HTTPException(403, "CSRF 校验失败")
    return user
