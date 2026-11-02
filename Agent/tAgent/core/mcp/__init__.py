"""tAgent 的外部 MCP Client。

让 tAgent 能连接外部 MCP Server（Streamable HTTP），并把对方提供的工具以
Function Calling 的形式注入到 Agent 的工具集合中，与本地工具（RunCli / fetchweb /
loadSkill 等）统一参与调用流程。

典型用法（在异步上下文里）：

.. code-block:: python

    from core.mcp import load_mcp_servers, discover_mcp_tool_specs

    servers, cfg_warnings = load_mcp_servers()          # 读 .mcp.json（同步）
    specs, conn_warnings = await discover_mcp_tool_specs(servers)
    agent = build_agent(settings, extra_tools=specs)     # 注入到 Agent
"""

from core.mcp.client import (
    MCPSdkNotInstalled,
    call_server_tool,
    list_server_tools,
)
from core.mcp.config import (
    MCP_CONFIG_FILENAME,
    MCPServerConfig,
    find_mcp_config,
    load_mcp_servers,
)
from core.mcp.discovery import discover_mcp_tool_specs, exposed_tool_name

__all__ = [
    "MCP_CONFIG_FILENAME",
    "MCPSdkNotInstalled",
    "MCPServerConfig",
    "call_server_tool",
    "discover_mcp_tool_specs",
    "exposed_tool_name",
    "find_mcp_config",
    "list_server_tools",
    "load_mcp_servers",
]
