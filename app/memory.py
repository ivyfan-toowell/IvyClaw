"""按用户隔离的短期、episodic、semantic 记忆与偏好服务。"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import ValidationError

from app.schemas import (ConversationRecord, ConversationSummary, ConversationTurn, MemoryExtraction, MemoryFact,
                         PreferencePatch, UserMemory, UserPreferences)
from infra.logging import get_logger
from middleware.concurrency import LLMConcurrencyMiddleware

logger = get_logger()
# 不把密钥/密码、认证令牌等存为长期事实。
_SENSITIVE = re.compile(r"password|密码|secret|api[_ -]?key|token|令牌|sk-[a-zA-Z0-9]", re.IGNORECASE)


def _snippet(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    prefix = budget // 2
    return text[:prefix] + "\n…\n" + text[-(budget - prefix - 3):]


async def extract_user_memory(text: str) -> MemoryExtraction:
    """只从用户原文提取明确事实和偏好，禁止从助手回复推断用户属性。"""
    from agent.main import build_model
    agent = create_agent(
        model=build_model(),
        system_prompt=("你是用户记忆提取器。只提取用户本次明确表达、对未来协作有用的稳定事实和偏好。"
                       "忽略问题中的假设、引用内容、临时任务要求；禁止猜测敏感属性，禁止保存密码、密钥或令牌。"
                       "用户要求不要记住的信息不保存。每项 evidence 必须逐字引用用户原文。"
                       "事实 key 使用 ASCII snake_case，同类事实使用稳定 key。没有可记信息就返回空列表。"),
        response_format=ToolStrategy(MemoryExtraction),
        middleware=[LLMConcurrencyMiddleware()],
    )
    sample = text if len(text) <= 16000 else text[:8000] + "\n…\n" + text[-8000:]
    result = await agent.ainvoke({"messages": [{"role": "user", "content": sample}]}, config={"recursion_limit": 20})
    return MemoryExtraction.model_validate(result["structured_response"])


class MemoryService:
    """复用 LangGraph Store；身份由调用方认证绑定，不接受工具提供的 user_id。"""

    def __init__(self, store: Any, user_id: str, tenant_id: str = "default",
                 channel: str = "web", redis: Any = None) -> None:
        """固定身份命名空间，Web/API 账户共享记忆，飞书标识独立隔离。"""
        identity_scope = "account" if channel in {"web", "api", "webhook"} else channel
        self.store = store
        self.namespace = ("ivyclaw_memory", tenant_id, identity_scope, user_id)
        self.redis = redis

    @asynccontextmanager
    async def _write_lock(self) -> AsyncIterator[None]:
        if self.redis is None:
            yield
        else:
            digest = hashlib.sha256(json.dumps(self.namespace).encode()).hexdigest()
            async with self.redis.lock("memory-lock:" + digest, timeout=30, blocking_timeout=10):
                yield

    async def preferences(self) -> UserPreferences:
        """读取账户偏好，首次访问返回默认值。"""
        item = await self.store.aget(self.namespace + ("profile",), "preferences")
        return UserPreferences.model_validate(item.value) if item else UserPreferences()

    async def update_preferences(self, patch: PreferencePatch) -> UserPreferences:
        """合并明确更新项，保留其他偏好。"""
        async with self._write_lock():
            preferences = await self.preferences()
            data = {**preferences.model_dump(), **patch.model_dump(exclude_unset=True, exclude_none=True)}
            preferences = UserPreferences.model_validate(data)
            await self.store.aput(self.namespace + ("profile",), "preferences", preferences.model_dump(mode="json", by_alias=True))
            return preferences

    async def remember_fact(self, fact: MemoryFact, user_text: str) -> MemoryFact:
        """只保存有当前用户原文证据且不含凭据的事实。"""
        if fact.evidence not in user_text or _SENSITIVE.search(fact.key + fact.value + fact.evidence):
            raise ValueError("长期记忆必须有用户原文证据，且不能包含认证凭据")
        if not (await self.preferences()).remember_facts:
            raise ValueError("用户已关闭长期事实记忆")
        await self.store.aput(self.namespace + ("semantic",), fact.key, fact.model_dump(mode="json", by_alias=True))
        return fact

    async def conversation(self, conversation_id: str) -> ConversationRecord | None:
        """读取当前用户的指定会话，其他用户命名空间不可见。"""
        key = hashlib.sha256(conversation_id.encode()).hexdigest()
        item = await self.store.aget(self.namespace + ("conversations",), key)
        return ConversationRecord.model_validate(item.value) if item else None

    async def conversations(self) -> list[ConversationSummary]:
        """返回最近会话列表，不将完整历史自动注入模型。"""
        items = await self.store.asearch(self.namespace + ("conversation_index",), limit=200)
        records = [ConversationSummary.model_validate(item.value) for item in items]
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    async def recall(self, query: str = "", limit: int = 8) -> UserMemory:
        """在 semantic 事实和近期 episodic 索引中做有界关键词召回。"""
        limit = max(1, min(limit, 20))
        items = await self.store.asearch(self.namespace + ("semantic",), limit=200)
        facts = [MemoryFact.model_validate(item.value) for item in items]
        index = await self.store.aget(self.namespace + ("profile",), "episodes")
        previews = index.value.get("previews", []) if index else []
        episodes = [ConversationTurn.model_validate(value) for value in previews]
        terms = set(re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", query.lower()))

        def score(text: str) -> int:
            return sum(term in text.lower() for term in terms)

        facts.sort(key=lambda fact: (score(fact.key + " " + fact.value), fact.updated_at), reverse=True)
        episodes.sort(key=lambda turn: (score(turn.user_text), turn.created_at), reverse=True)
        return UserMemory(preferences=await self.preferences(), semantic=facts[:limit], episodic=episodes[:limit])

    async def context(self, conversation_id: str, query: str) -> str:
        """组合偏好、最近六轮、相关事实和经历，控制注入长度。"""
        memory = await self.recall(query, limit=4)
        conversation = await self.conversation(conversation_id)
        recent = conversation.turns[-6:] if conversation else []
        data = {
            "preferences": memory.preferences.model_dump(by_alias=True),
            "semantic": [{"key": fact.key, "value": fact.value} for fact in memory.semantic],
            "recentTurns": [{"user": _snippet(turn.user_text, 2000), "assistant": _snippet(turn.reply, 2000)} for turn in recent],
            "episodic": [{"user": _snippet(turn.user_text, 1000), "outcome": _snippet(turn.reply, 1000)}
                         for turn in memory.episodic if turn.conversation_id != conversation_id],
        }
        encoded = json.dumps(data, ensure_ascii=False)
        while len(encoded) > 24000 and data["recentTurns"]:
            data["recentTurns"].pop(0)
            encoded = json.dumps(data, ensure_ascii=False)
        while len(encoded) > 24000 and data["episodic"]:
            data["episodic"].pop()
            encoded = json.dumps(data, ensure_ascii=False)
        return encoded

    async def record_turn(self, conversation_id: str, user_text: str, reply: str,
                          extraction: MemoryExtraction | None = None) -> ConversationTurn:
        """每次完成对话先保存经历与历史，再尽力提取稳定事实和偏好。"""
        turn = ConversationTurn(turn_id=uuid4().hex, conversation_id=conversation_id, user_text=user_text, reply=reply)
        async with self._write_lock():
            record = await self.conversation(conversation_id)
            if record is None:
                record = ConversationRecord(conversation_id=conversation_id, title=user_text[:40])
            record.turns = (record.turns + [turn])[-200:]
            record.updated_at = turn.created_at
            await self.store.aput(self.namespace + ("episodic",), turn.turn_id, turn.model_dump(mode="json", by_alias=True))
            await self.store.aput(self.namespace + ("conversations",), hashlib.sha256(conversation_id.encode()).hexdigest(),
                                  record.model_dump(mode="json", by_alias=True))
            summary = ConversationSummary(conversation_id=conversation_id, title=record.title,
                                          updated_at=record.updated_at, turn_count=len(record.turns))
            await self.store.aput(self.namespace + ("conversation_index",), hashlib.sha256(conversation_id.encode()).hexdigest(),
                                  summary.model_dump(mode="json", by_alias=True))
            index = await self.store.aget(self.namespace + ("profile",), "episodes")
            keys = index.value.get("keys", []) if index else []
            previews = index.value.get("previews", []) if index else []
            preview = turn.model_copy(update={"user_text": _snippet(user_text, 1000), "reply": _snippet(reply, 1000)})
            await self.store.aput(self.namespace + ("profile",), "episodes", {
                "keys": (keys + [turn.turn_id])[-100:],
                "previews": (previews + [preview.model_dump(mode="json", by_alias=True)])[-100:],
            })
        if not (await self.preferences()).remember_facts:
            return turn
        try:
            if extraction is None:
                extraction = await extract_user_memory(user_text)
            for fact in extraction.facts:
                try:
                    await self.remember_fact(fact, user_text)
                except ValueError:
                    logger.warning("忽略缺少证据或包含敏感信息的记忆事实")
            for preference in extraction.preferences:
                if preference.evidence not in user_text or _SENSITIVE.search(preference.evidence):
                    continue
                try:
                    patch = PreferencePatch.model_validate({preference.field: preference.value})
                    await self.update_preferences(patch)
                except ValidationError:
                    logger.warning("忽略无效的偏好更新")
        except Exception:
            # 只隔离可选的 LLM 提取失败；对话/经历已保存，不转换成客户端错误。
            logger.exception("记忆提取失败，已保留 episodic 记录")
        return turn
