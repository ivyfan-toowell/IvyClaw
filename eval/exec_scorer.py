"""
eval/exec_scorer.py —— 客观评分：沙箱 pytest 通过率 + 规范静态检查
复用第 11 章的沙箱（create_one_sandbox / seed_project / destroy_sandbox）。
客观评分结果是 0/1（测试过则 1）——能运行验证的任务结果是确定的，不需要模糊打分。
"""
import ast

from agent.main import agent_runtime_session


async def score_by_execution(agent, case: dict) -> dict:
    """让 agent 在沙箱里实现，写入隐藏测试，跑 pytest，按通过情况打分。"""
    # 代码题必须让 Agent 修改代码和隐藏测试在同一个沙箱内执行。
    async with agent_runtime_session(thread_id=f"eval-{case['id']}") as runtime:
        agent = runtime.agent
        sandbox = runtime.sandbox
        # ① agent 在沙箱里实现
        await agent.ainvoke(
            {"messages": [{"role": "user", "content": case["issue"]}]},
            config={"configurable": {"thread_id": f"eval-{case['id']}"}},
        )
        # ② 写入隐藏测试（覆盖 agent 可能写的同名测试）
        sandbox.upload_files([(case["test_file"], case["test_code"].encode("utf-8"))])
        # ③ 跑 pytest 看通过
        r = sandbox.execute("cd /home/agent && python -m pytest -q 2>&1 | tail -5")
        passed = ("passed" in r.output
                  and "failed" not in r.output and "error" not in r.output.lower())
        # ④ 静态检查：取回代码验规范（货币没用 float、函数有类型注解）
        target = case.get("target_file", "")
        code = b""
        if target:
            dl = sandbox.download_files([f"/home/agent/{target}"])
            code = dl[0].content if dl and dl[0].content else b""
        static = _static_checks(code)
        return {
            "id": case["id"], "category": "exec",
            "score": 1.0 if passed else 0.0,      # 客观：过则 1，不过则 0
            "static": static,                     # 规范遵守的附加维度
            "detail": r.output[-200:],
        }


def _static_checks(code: bytes) -> dict:
    """
    AST 静态检查：量化 AGENTS.md 铁律有没有被遵守。
    简化版：出现 float( 调用就算违规（真实项目要更精细判断是否用于金额，
    比如只在金额相关变量/函数里查；这里粗判，作为示意）。
    """
    out = {"no_float_money": True, "has_type_hints": True}
    try:
        tree = ast.parse(code.decode("utf-8", errors="replace"))
    except SyntaxError:
        return {"no_float_money": False, "has_type_hints": False, "parse_error": True}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
            out["no_float_money"] = False
        if isinstance(node, ast.FunctionDef):
            if node.returns is None or any(a.annotation is None for a in node.args.args):
                out["has_type_hints"] = False
    return out
