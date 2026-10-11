"""Web 账户注册、登录和退出接口。"""
from fastapi import APIRouter, Depends, Request, Response, HTTPException

from api.schemas import AuthUser, Credentials
from gateway.users import COOKIE_NAME, authenticate, create_session, require_user, session_key
from infra.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def check_origin(request: Request) -> None:
    """防止跨站注册/登录种植会话。"""
    origin = request.headers.get("origin")
    allowed = [str(request.base_url).rstrip("/"), *get_settings().allowed_origins]
    if origin and origin not in allowed:
        raise HTTPException(403, "不允许的来源")


@router.post("/register", response_model=AuthUser, status_code=201)
async def register(credentials: Credentials, request: Request, response: Response) -> AuthUser:
    """创建账户并登录。"""
    check_origin(request)
    user = await authenticate(request, credentials, register=True)
    await create_session(request, response, user)
    return user


@router.post("/login", response_model=AuthUser)
async def login(credentials: Credentials, request: Request, response: Response) -> AuthUser:
    """验证凭据并轮换会话。"""
    check_origin(request)
    user = await authenticate(request, credentials, register=False)
    await create_session(request, response, user)
    return user


@router.get("/me", response_model=AuthUser)
async def me(response: Response, user: AuthUser = Depends(require_user)) -> AuthUser:
    """返回当前账户，供刷新页面恢复身份。"""
    response.headers["Cache-Control"] = "no-store"
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, user: AuthUser = Depends(require_user)) -> None:
    """撤销服务端会话并清除 Cookie。"""
    await request.app.state.redis.delete(session_key(request.cookies[COOKIE_NAME]))
    response.delete_cookie(COOKIE_NAME, path="/")
