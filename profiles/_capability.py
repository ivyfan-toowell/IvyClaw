"""profiles/_capability.py —— 检测当前 deepagents 是否支持 Harness Profile"""

def harness_profile_available() -> bool:
    """能 import 就支持；否则当前版本太旧（profile 是 beta 特性）。"""
    try:
        from deepagents import HarnessProfile, register_harness_profile  # noqa: F401
        return True
    except Exception:
        return False