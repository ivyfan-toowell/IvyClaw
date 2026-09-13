
"""api/schemas.py —— 对外 HTTP 契约（Pydantic v2）"""
from pydantic import BaseModel, Field


class IssueRequest(BaseModel):
    """提交一个开发 Issue。"""
    issue: str = Field(..., min_length=1, description="要 DevMate 处理的开发任务描述")
    user_id: str = Field("anonymous", description="提交者标识")
    channel: str = Field("api", description="来源渠道（api/cli/web/feishu…）")
    thread_id: str | None = Field(
        None, description="会话线程 ID；传入相同 thread_id 可在同一对话上下文继续（断点续跑）"
    )


class IssueResponse(BaseModel):
    """Issue 处理结果。"""
    thread_id: str = Field(..., description="本次会话的线程 ID（下次带上它可续聊）")
    reply: str = Field(..., description="DevMate 的最终回复")
    approved: bool | None = Field(None, description="若有 reviewer 审查结论，是否通过")


class HealthResponse(BaseModel):
    status: str
    detail: str | None = None