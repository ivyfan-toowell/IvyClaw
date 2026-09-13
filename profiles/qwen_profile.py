"""profiles/qwen_profile.py —— 为 qwen（OpenAI 兼容）定制的 Harness Profile

在官方内置的 "openai" profile 之上叠加 qwen 适配（合并语义是叠加，不是替换）。
注册后，create_deep_agent 选中 openai 兼容模型时自动应用——调用点一行不用改。

⚠️ Harness Profile 需要 deepagents>=0.5.4（public beta）。先用 _capability 自检。
"""
from deepagents import HarnessProfile, register_harness_profile


# 版本化：标注"当前这套 Harness 调校是哪一版"，便于在日志/trace 里追踪与回滚
QWEN_PROFILE_VERSION = "qwen-profile-v1"


def _qwen_profile() -> HarnessProfile:
    return HarnessProfile(
        # ① 摘掉对 qwen 无用的 Anthropic 提示词缓存中间件（本章的核心动作）
        #    这正是 3.1 那个"在你栈里空转"的中间件。excluded_middleware 用字符串时
        #    匹配的是【类名】（官方示例即 {"SummarizationMiddleware"} 这种写法）。
        #    ⚠️ 不能排除 FilesystemMiddleware / SubAgentMiddleware / permission 中间件（会 ValueError）。
        excluded_middleware={"AnthropicPromptCachingMiddleware"},

        # ② 给 qwen 追加适配性的提示词后缀（按你的实测调整内容）
        #    放在最后生效；这里约束输出简洁、工具调用规范——是常见的国产模型适配点。
        system_prompt_suffix=(
            "输出简洁、工具调用时必须严格遵循工具 schema，不得臆造参数；"
            "若工具调用失败，先阅读错误信息再决定下一步，不要重复相同调用；"
            "需要结构化输出时，只输出指定结构，不添加额外解释。"
        ),
    )


def register_qwen_profiles() -> None:
    """注册 qwen 的 Harness Profile（在应用/脚本启动早期调用一次）。"""
    register_harness_profile("openai:qwen-max", _qwen_profile())
    register_harness_profile("openai:qwen-plus", _qwen_profile())
    register_harness_profile("openai:qwen-turbo", _qwen_profile())


def register_all_profiles():
    return None