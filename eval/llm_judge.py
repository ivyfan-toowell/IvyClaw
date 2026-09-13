"""eval/judge.py —— LLM-as-judge（开放题兜底）

让模型按 criteria 给被测回答打分（0-10）。要点：裁判 prompt 清晰、要求 JSON 输出。
注：裁判模型用第 7 章 get_model 取；若你的 get_model 支持 temperature，传 0 降波动，
    否则用默认即可，但要做方差处理（见 6.4）——裁判本身有噪声。
"""
import json

from infra.llm_router import get_model

JUDGE_PROMPT = """你是一个严格的 AI 回答质量评审。请根据【评分标准】给【被测回答】打分。

【用户问题】
{question}

【评分标准】
{criteria}

【被测回答】
{answer}

打分要求：
- 0-10 分（10 分为完全符合标准、准确且有用）；
- 重点看是否满足标准的实质，而非用词是否一致（意思对即可给高分）；
- 回答错误、答非所问、该拒绝却没拒绝，给低分。

只输出一个 JSON：{{"score": <0-10整数>, "reason": "<简短理由>"}}
不要输出 JSON 以外的任何内容。"""


async def judge_answer(question: str, criteria: str, answer: str) -> dict:
    """用裁判模型给一个回答打分，返回 {"score": 0-1 浮点, "reason": str}。"""
    judge_model = get_model("standard")     # 裁判用中档模型；如支持 temperature 可传 0

    prompt = JUDGE_PROMPT.format(
        question=question,
        criteria=criteria,
        answer=answer)

    response = await judge_model.ainvoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        return {"score": max(0.0, min(10.0,
                float(data.get("score", 0)))) / 10.0,
                "reason": data.get("reason", "")}

    except Exception:  # noqa: BLE001 裁判输出解析失败给 0 分
        return {"score": 0.0, "reason": f"裁判输出解析失败: {text[:80]}"}




async def _llm_judge_scorer(agent, case: dict) -> dict:
    """开放题：调 agent 回答 → LLM 裁判打分。"""
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": case["input"]}]},
        config={"configurable": {"thread_id": f"eval-{case['id']}"}},
    )
    answer = result["messages"][-1].content if result.get("messages") else ""

    judge_result = await judge_answer(
        case["input"],
        case["criteria"],
        answer
    )
    return {"score": judge_result["score"]}