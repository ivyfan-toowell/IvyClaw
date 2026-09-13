"""tools/search_tools.py —— DevMate 的检索工具

把"联网搜索 / 取网页内容"封装成工具。这里给出最简形态（你可换成 Tavily/Exa 等）。
I/O 型工具用 async，避免阻塞事件循环（本课异步基调）。
"""
"""tools/search_tools.py —— DevMate 的检索工具

提供：
1. web_search：联网搜索
2. fetch_url：抓取指定网页正文
"""

import os
from dotenv import load_dotenv

load_dotenv()
from langchain.tools import tool
from tavily import AsyncTavilyClient

def _get_client() -> AsyncTavilyClient:
    """创建 Tavily 异步客户端。"""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("未配置环境变量 TAVILY_API_KEY")
    return AsyncTavilyClient(api_key=api_key)


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """联网搜索，返回与 query 最相关的若干结果摘要。
    用于查询外部最新信息，例如最新文档、报错原因、库的新版本用法等。
    """
    client = _get_client()

    response = await client.search(
        query=query,
        max_results=max_results,
        search_depth="basic",
    )

    results = response.get("results", [])

    if not results:
        return "未搜索到相关结果。"

    lines = []

    for i, item in enumerate(results, start=1):
        title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")

        lines.append(
            f"{i}. {title}\n"
            f"URL: {url}\n"
            f"摘要: {content}"
        )

    return "\n\n".join(lines)


@tool
async def fetch_url(url: str) -> str:
    """抓取指定 URL 的网页正文，用于阅读某个具体网页或文档。"""
    client = _get_client()

    response = await client.extract(url)

    results = response.get("results", [])

    if not results:
        return f"未能抓取网页内容：{url}"

    content = results[0].get("raw_content", "")

    if not content:
        return f"网页存在，但没有提取到正文：{url}"

    return content[:12000]