from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime, timezone
from typing import Literal
from typing import Annotated
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel


# 商品条目模型
class Item(BaseModel):
    unit_price: Decimal = Field(..., description="商品单价")
    quantity: int = Field(..., description="商品数量")


# 报价请求模型
class QuoteRequest(BaseModel):
    items: list[Item] = Field(..., description="一组商品条目")


class QuoteResponse(QuoteRequest):
    """报价结果，保留已有字段名称和 Decimal 精度。"""
    total_amount: Decimal


class MemoryModel(BaseModel):
    """记忆模块统一的 camelCase API 模型。"""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class UserPreferences(MemoryModel):
    """用户明确表达的协作偏好。"""
    preferred_language: str = Field(default="zh-CN", min_length=2, max_length=40)
    response_style: Literal["concise", "detailed"] = "concise"
    collaboration_style: str = Field(default="先说明目标，再执行并报告验证结果", max_length=500)
    tech_stack: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=20)
    timezone: str = Field(default="Asia/Shanghai", max_length=80)
    remember_facts: bool = True


class PreferencePatch(MemoryModel):
    """只更新用户提供的偏好字段。"""
    preferred_language: str | None = Field(default=None, min_length=2, max_length=40)
    response_style: Literal["concise", "detailed"] | None = None
    collaboration_style: str | None = Field(default=None, max_length=500)
    tech_stack: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=80)
    remember_facts: bool | None = None


class MemoryFact(MemoryModel):
    """带用户原文证据的 semantic 事实。"""
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    value: str = Field(min_length=1, max_length=1000)
    evidence: str = Field(min_length=1, max_length=1000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PreferenceEvidence(MemoryModel):
    """每项自动偏好更新必须引用当前用户原文。"""
    field: Literal["preferred_language", "response_style", "collaboration_style", "tech_stack", "timezone"]
    value: str | list[str]
    evidence: str = Field(min_length=1, max_length=1000)


class MemoryExtraction(MemoryModel):
    """仅提取当前用户明确表达且允许记住的信息。"""
    facts: list[MemoryFact] = Field(default_factory=list, max_length=5)
    preferences: list[PreferenceEvidence] = Field(default_factory=list, max_length=5)


class ConversationTurn(MemoryModel):
    """一次完成的对话，同时构成 episodic 记忆。"""
    turn_id: str
    conversation_id: str
    user_text: str
    reply: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationRecord(MemoryModel):
    """服务端持久会话记录及有界的最近对话窗口。"""
    conversation_id: str
    title: str
    turns: list[ConversationTurn] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationSummary(MemoryModel):
    """会话列表只返回索引，避免一次下载所有聊天全文。"""
    conversation_id: str
    title: str
    updated_at: datetime
    turn_count: int


class UserMemory(MemoryModel):
    """用户偏好、semantic 事实和最近 episodic 经历。"""
    preferences: UserPreferences
    semantic: list[MemoryFact] = Field(default_factory=list)
    episodic: list[ConversationTurn] = Field(default_factory=list)
