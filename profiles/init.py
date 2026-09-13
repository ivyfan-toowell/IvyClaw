"""profiles/__init__.py —— 在应用启动时注册所有 Harness Profile"""

from profiles.qwen_profile import register_qwen_profiles
from infra.logging import get_logger

logger = get_logger()

def register_all_profiles() -> None:
    """注册本项目所有 Harness Profile。在应用/脚本启动早期调用一次。"""
    register_qwen_profiles()
    logger.info("Harness Profiles 已注册")





