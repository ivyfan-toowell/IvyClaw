
"""api/schemas.py —— 对外 HTTP 契约（Pydantic v2）"""
from pydantic import BaseModel, Field
from pydantic import ConfigDict, AliasChoices, field_validator


class Credentials(BaseModel):
    """注册和登录凭据，密码长度有上限以限制哈希资源。"""
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128, repr=False)


class AuthUser(BaseModel):
    """登录身份与会话 CSRF 校验值。"""
    model_config = ConfigDict(populate_by_name=True)
    user_id: str = Field(alias="userId")
    username: str
    csrf_token: str = Field(alias="csrfToken", repr=False)


class MessageRequest(BaseModel):
    """兼容已有请求字段；身份只从服务端认证取得。"""
    model_config = ConfigDict(populate_by_name=True)
    text: str = Field(min_length=1, max_length=100000)
    conversation_id: str = Field(default="default", min_length=1, max_length=200,
                                 validation_alias=AliasChoices("conversation_id", "conversationId"))
    source: str = "web"

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        """拒绝空白任务，避免触发无意义的模型调用。"""
        value = value.strip()
        if not value:
            raise ValueError("任务文本不能为空")
        return value


class MessageResponse(BaseModel):
    """保留通用 Webhook 的已有响应结构。"""
    code: int = 0
    reply: str


class JobSubmission(BaseModel):
    """保留既有队列提交响应。"""
    job_id: str
    status: str = "queued"


class JobResult(BaseModel):
    """既有 worker 最终结果契约。"""
    reply: str
    conversation_id: str


class JobResponse(BaseModel):
    """已授权任务的执行状态与结果。"""
    job_id: str
    status: str
    result: JobResult | None = None
    error: str | None = None


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
