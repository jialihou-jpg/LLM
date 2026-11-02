"""MCP 客户端连接（Streamable HTTP）。

封装一次"连接 → initialize → list_tools / call_tool → 关闭"的完整流程。
使用 MCP 官方 Python SDK 的标准接口：``streamable_http_client`` + ``ClientSession``。

为了避免长连接生命周期管理的复杂性（TUI 是长进程，但每个 MCP Server 的连接在
一次工具发现或一次工具调用时临时建立、用完即关），这里采用**按需连接**模式：
发现工具和每次调用工具都各自建立一次短期连接。某个 Server 连不上只会影响它自己，
不会拖累其他工具。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.mcp.config import MCPServerConfig

if TYPE_CHECKING:
    from mcp.types import Tool as MCPTool


class MCPSdkNotInstalled(RuntimeError):
    """未安装 mcp SDK 时抛出，提示用户安装。"""


def _import_sdk() -> tuple[Any, Any, Any]:
    """惰性导入 mcp SDK；未安装时抛出带安装指引的清晰错误。"""
    try:
        from mcp import ClientSession  # noqa: PLC0415
        from mcp.client.streamable_http import (  # noqa: PLC0415
            create_mcp_http_client,
            streamable_http_client,
        )

        return ClientSession, streamable_http_client, create_mcp_http_client
    except ImportError as exc:  # pragma: no cover - 依赖缺失分支
        raise MCPSdkNotInstalled(
            "未安装 mcp SDK，请先运行：pip install \"mcp\"（或 pip install -e \".[mcp]\"）"
        ) from exc


async def list_server_tools(server: MCPServerConfig) -> list[MCPTool]:
    """连接 MCP Server 并返回其全部工具（name / description / inputSchema）。"""
    ClientSession, streamable_http_client, create_http_client = _import_sdk()
    http_client = create_http_client(headers=server.headers or None)
    async with streamable_http_client(server.url, http_client=http_client) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return list(result.tools)


async def call_server_tool(
    server: MCPServerConfig, tool_name: str, arguments: dict[str, Any] | None
) -> str:
    """连接 MCP Server 并调用指定工具，把结果格式化成可回传给 LLM 的文本。"""
    ClientSession, streamable_http_client, create_http_client = _import_sdk()
    http_client = create_http_client(headers=server.headers or None)
    async with streamable_http_client(server.url, http_client=http_client) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments or {})
            return _format_result(result)


def _format_result(result: Any) -> str:
    """把 CallToolResult 转成纯文本，正确处理文本内容、结构化数据与错误。"""
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
        else:
            # 非文本内容（如 image / resource），退化为其字符串表示
            parts.append(str(item))

    body = "\n".join(parts).strip() if parts else ""
    if getattr(result, "is_error", False):
        return f"MCP 工具执行返回错误：{body or '(无详情)'}"
    return body or "(工具执行成功，但没有返回内容)"


__all__ = [
    "MCPSdkNotInstalled",
    "call_server_tool",
    "list_server_tools",
]
