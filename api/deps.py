"""api/deps.py —— 依赖注入：从 app.state 取共享资源

路由通过 Depends 拿到 checkpointer/store，而不是直接访问全局，
便于测试时替换、也让依赖关系显式。
"""
from fastapi import Request


def get_checkpointer(request: Request):
    """取在 lifespan 里建好的 AsyncPostgresSaver。"""
    return request.app.state.checkpointer


def get_store(request: Request):
    """取在 lifespan 里建好的 AsyncPostgresStore。"""
    return request.app.state.store