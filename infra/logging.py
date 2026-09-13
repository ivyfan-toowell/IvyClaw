"""infra/logging.py —— 基于 loguru 的统一日志配置"""
import sys
from pathlib import Path

from loguru import logger
from infra.settings import get_settings

_CONFIGURED = False


def setup_logging() -> None:
    """初始化全局日志。幂等：多次调用只生效一次。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = get_settings().log_level

    # 清掉 loguru 默认 handler，重新按需添加
    logger.remove()

    # ---- 控制台输出：彩色、带模块位置 ----
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        backtrace=True,
        diagnose=True,           # 打印异常时显示变量值，方便排错
        colorize=True,
    )

    # ---- 文件输出：按 10 MB 轮转，保留 7 天，压缩旧文件 ----
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "shanyang_{time:YYYY-MM-DD}.log",
        level=level,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,            # 多进程/异步安全
    )

    _CONFIGURED = True


def get_logger():
    """业务统一入口。loguru 的 logger 是全局单例，
    会自动捕获调用方的 module/function/line，不用传 __name__。"""
    setup_logging()
    return logger