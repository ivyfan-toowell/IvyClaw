"""tools/mcp.py —— MCP 工具接入管理（langchain-mcp-adapters）

依赖：uv sync --extra mcp

工程化要点：
- 配置化：server 列表来自 settings（或显式传入），不写死；
- 容错：逐个 server 取工具，某个连不上只 warning 跳过，不让整个 agent 起不来；
- 单一入口：build_agent 只需调 MCPManager.get_tools()，不关心连接细节。

注意（高并发）：本类每次 get_tools() 会新建 client。后半做成高并发服务时，
应在 FastAPI lifespan 里建一次、全程复用（见第 9 章），避免每请求重连所有 server。
"""
from __future__ import annotations

from langchain_mcp_adapters.client import MultiServerMCPClient

from infra.settings import get_settings
from infra.logging import get_logger

logger = get_logger()


class MCPManager:
    """管理一组 MCP server 的连接与工具获取。

    用法：
        mgr = MCPManager.from_settings()        # 从配置构建
        tools = await mgr.get_tools()           # 容错地取回所有可用工具
    """

    def __init__(self, servers: dict[str, dict]):
        # servers: {"name": {"transport": "http"/"stdio", ...}}
        self.servers = servers or {}

    @classmethod
    def from_settings(cls) -> "MCPManager":
        """从配置中枢读取 MCP server 列表构建（推荐）。"""
        return cls(get_settings().mcp_servers)

    async def get_tools(self) -> list:
        """逐个 server 取工具，单个失败不影响其余（容错核心）。

        返回：所有成功连接的 server 的工具合并列表。全部失败则返回空列表，
        DevMate 仍能用内置工具与自定义工具正常工作。
        """
        if not self.servers:
            logger.info("未配置任何 MCP server，跳过 MCP 工具加载")
            return []

        all_tools: list = []
        for name, conf in self.servers.items():
            try:
                # 单 server 单独建 client 取工具：这样一个 server 出错不波及其它
                client = MultiServerMCPClient({name: conf})
                tools = await client.get_tools()
                all_tools.extend(tools)
                logger.info("MCP server『{}』已接入，获取 {} 个工具", name, len(tools))
            except Exception as e:  # noqa: BLE001 容错：记录并跳过该 server
                logger.warning("MCP server『{}』接入失败，已跳过：{}", name, e)
        logger.info("MCP 工具加载完成，共 {} 个可用", len(all_tools))
        return all_tools