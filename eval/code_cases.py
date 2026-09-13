# eval/code_cases.py —— 带隐藏测试的编码用例（客观评分）
CODE_EVAL_CASES = [
    {
        "id": "exec-01",
        "category": "exec",
        "issue": "在 /home/agent/app/calc.py 实现 calc_total(items)，"
                 "items 形如 [{'price':'10.00','qty':2}]，金额用 Decimal，返回总价字符串。",
        "target_file": "app/calc.py",                # 相对 workdir，用于静态检查取回
        "test_file": "/home/agent/tests/test_calc.py",
        "test_code": (
            "from decimal import Decimal\n"
            "from app.calc import calc_total\n"
            "def test_basic():\n"
            "    assert calc_total([{'price':'10.00','qty':2}]) == '20.00'\n"
            "def test_multi():\n"
            "    assert calc_total([{'price':'1.50','qty':3},{'price':'2.00','qty':1}]) == '6.50'\n"
        ),
    },
    # ... 更多编码用例，每条都带可运行的隐藏测试 ...
]