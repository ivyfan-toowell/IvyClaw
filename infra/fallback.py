"""
infra/fallback.py —— 模型 fallback(主模型失败退备用)

主模型(strong 档)限流/报错时,自动退到备用模型,保证可用性。
接入点就是第 7 章的 llm_router：从 model_tiers 取主/备模型对象。
导入路径(官方确认)：from langchain.agents.middleware import ModelFallbackMiddleware
"""
from langchain.agents.middleware import ModelFallbackMiddleware

from infra.llm_router import get_model


def build_fallback_middleware() -> ModelFallbackMiddleware:
    """主用 strong,失败退 standard,再退 cheap——按 model_tiers 配。

    主模型仍由 create_deep_agent(model=get_model("strong")) 指定;
    这条中间件在主模型抛错时依次尝试下面的备用模型(不含主模型本身)。
    ModelFallbackMiddleware 接收的是备用模型,可传字符串或 BaseChatModel 实例。
    """
    return ModelFallbackMiddleware(
        get_model("standard"),   # 第一备用
        get_model("cheap"),      # 第二备用
    )


