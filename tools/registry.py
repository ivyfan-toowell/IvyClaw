"""tools/registry.py —— 工具注册中心（按需装配，热插拔）

把各模块的工具集中登记；build_agent 按需要取一组工具，而不是写死一长串 import。
这样新增/停用某类工具，只改这里一处。
"""
from langchain.tools import tool as _tool_type  # 仅用于类型直觉，可省

from tools.git_tools import git_status, git_diff, git_commit, open_pull_request
from tools.search_tools import web_search, fetch_url
from tools.test_tools import run_pytest

# 按用途分组登记
_GROUPS: dict[str, list] = {
    "git": [git_status, git_diff, git_commit, open_pull_request],
    "search": [web_search, fetch_url],
    "test": [run_pytest],
}


def get_tools(*groups: str) -> list:
    """按组名取工具列表。例如 get_tools("git", "search")。
    不传参则返回所有已登记工具。"""
    if not groups:
        return [t for ts in _GROUPS.values() for t in ts]
    out: list = []
    for g in groups:
        if g not in _GROUPS:
            raise KeyError(f"未知工具组：{g}，可选：{list(_GROUPS)}")
        out.extend(_GROUPS[g])
    return out






