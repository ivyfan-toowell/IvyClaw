"""eval/run_eval.py —— 跑一轮 Eval：编码题客观评分 + 开放题 LLM 裁判，多次采样报方差

运行：uv run python -m eval.run_eval
（编码题会起沙箱跑测试、开放题调裁判模型，有成本，几分钟，正常）
"""
import asyncio
import json
import statistics
from datetime import datetime, timezone

from agent.main import agent_session
from eval.open_cases import EVAL_CASES               # 开放题（domain/safety/general）
from eval.code_cases import CODE_EVAL_CASES       # 编码题（exec）
from eval.exec_scorer import score_by_execution
from eval.llm_judge import _llm_judge_scorer

_REPEATS = 3                  # 每条重复次数（降随机性；越多越稳越贵）
_CONCURRENCY = 3
BASELINE_FILE = "eval/baseline.json"


async def _eval_repeated(agent, sem, case, scorer) -> dict:
    """一条用例跑 N 次，报均值 ± 标准差。"""
    scores = []
    for _ in range(_REPEATS):
        async with sem:
            result = await scorer(agent, case)
            scores.append(result["score"])
    return {
        "id": case["id"],
        "category": case["category"],
        "mean": statistics.mean(scores),
        "std": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
        "scores": scores,
    }


async def main():
    async with agent_session(thread_id="eval-open-cases") as agent:
        sem = asyncio.Semaphore(_CONCURRENCY)

        tasks = []
        # 编码题会在评分器内部创建与 Agent 绑定的独立沙箱。
        for c in CODE_EVAL_CASES:
            tasks.append(_eval_repeated(None, sem, c, score_by_execution))
        # 开放题共享一个只在本轮 Eval 存活的 Agent。
        for c in EVAL_CASES:
            tasks.append(_eval_repeated(agent, sem, c, _llm_judge_scorer))

        print(f"开始 Eval：{len(CODE_EVAL_CASES)} 编码题 + {len(EVAL_CASES)} 开放题，每条 {_REPEATS} 次\n")
        results = await asyncio.gather(*tasks)

    for r in results:
        flag = "⚠️ 不稳定" if r["std"] > 0.2 else ""
        print(f"  [{r['id']:10s}] {r['mean']*10:.1f}/10 ± {r['std']*10:.1f}  {flag}")

    # 分维度汇总
    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r["mean"])
    print("\n=== 分维度均值 ===")


    cat_avgs = {}
    cat_stds = {}

    for cat, ms in sorted(by_cat.items()):
        cat_avgs[cat] = round(sum(ms) / len(ms), 3)
        # 这个维度内、各用例均值的波动，作为该维度的噪声带（见下文退化判定）
        cat_stds[cat] = round(statistics.pstdev(ms) if len(ms) > 1 else 0.0, 3)

        print(f"  {cat:8s}: {cat_avgs[cat]:.3f}  (±{cat_stds[cat]:.3f}, {len(ms)} 条)")

    overall = round(sum(r["mean"] for r in results) / len(results), 3)
    print(f"\n总体均值：{overall}")

    # 基线对比：退化判定 = 本次均值 < 基线均值 − 噪声带（掉出噪声范围才算真退化）
    try:
        with open(BASELINE_FILE, encoding="utf-8") as f:
            base = json.load(f)
        print("\n=== 对比基线 ===")

        regressed = False

        for cat, avg in cat_avgs.items():
            b = base.get("categories", {}).get(cat)
            if b is not None:
                # 噪声带：用基线存的该维度 std（没有就退回固定 0.05 兜底）
                noise = base.get("category_stds", {}).get(cat, 0.05)
                noise = max(noise, 0.03)   # 给个下限，避免 std=0 时过于严苛
                is_reg = avg < b - noise
                regressed = regressed or is_reg

                print(f"  {cat:8s}: {avg:.3f} (基线 {b:.3f}±{noise:.3f}, {avg-b:+.3f})"
                      f" {'❌ 退化' if is_reg else '✅'}")

        print("\n" + ("❌ 检测到退化，建议回滚或排查" if regressed else "✅ 未退化"))


    except FileNotFoundError:
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump({"overall": overall, "categories": cat_avgs,
                       "category_stds": cat_stds,                  # 把噪声带也存进基线
                       "saved_at": datetime.now(timezone.utc).isoformat()},
                      f, ensure_ascii=False, indent=2)
        print(f"\n（首次运行，已存为基线 → {BASELINE_FILE}）")


if __name__ == "__main__":
    asyncio.run(main())
