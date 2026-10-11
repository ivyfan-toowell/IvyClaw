"""账户偏好、记忆和服务端对话恢复接口。"""
from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import AuthUser
from app.memory import MemoryService
from app.schemas import ConversationRecord, ConversationSummary, PreferencePatch, UserMemory, UserPreferences
from gateway.users import require_user

router = APIRouter(tags=["memory"])


def user_memory(request: Request, user: AuthUser) -> MemoryService:
    """绑定当前登录身份与共享 Store。"""
    return MemoryService(request.app.state.store, user.user_id, redis=request.app.state.redis)


@router.get("/me/preferences", response_model=UserPreferences)
async def get_preferences(request: Request, user: AuthUser = Depends(require_user)) -> UserPreferences:
    """查看自己的协作偏好。"""
    return await user_memory(request, user).preferences()


@router.patch("/me/preferences", response_model=UserPreferences)
async def patch_preferences(patch: PreferencePatch, request: Request,
                            user: AuthUser = Depends(require_user)) -> UserPreferences:
    """更新自己的偏好，包括是否提取长期事实。"""
    return await user_memory(request, user).update_preferences(patch)


@router.get("/me/memory", response_model=UserMemory)
async def get_memory(request: Request, user: AuthUser = Depends(require_user)) -> UserMemory:
    """查看自己的近期经历与 semantic 事实。"""
    return await user_memory(request, user).recall(limit=20)


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(request: Request, user: AuthUser = Depends(require_user)) -> list[ConversationSummary]:
    """恢复当前账户的服务端会话。"""
    return await user_memory(request, user).conversations()


@router.get("/conversations/{conversation_id:path}", response_model=ConversationRecord)
async def get_conversation(conversation_id: str, request: Request,
                           user: AuthUser = Depends(require_user)) -> ConversationRecord:
    """读取自己的会话；猜测他人 ID 返回 404。"""
    record = await user_memory(request, user).conversation(conversation_id)
    if record is None:
        raise HTTPException(404, "会话不存在")
    return record
