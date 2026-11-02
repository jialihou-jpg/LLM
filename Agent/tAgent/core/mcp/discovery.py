"""把外部 MCP Server 的工具适配成 tAgent 的 :class:`ToolSpec`。

职责：
- 连接每个配置的 MCP Server，调用 ``list_tools()`` 拿到工具名、描述、参数 Schema；
- 为暴露给 LLM 的工具名加上服务器名前缀，避免不同 MCP Server 之间工具名冲突；
- 内部维护"暴露名 -> (服务器名, 原始工具名)"的映射；
- 把每个 MCP 工具包装成一个异步 handler，调用时按映射转发到对应服务器。

单个 MCP Server 连接失败时只记录一条 warning 并跳过，不影响其他 Server 与本地工具。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from core.mcp.client import call_server_tool, list_server_tools
from core.mcp.config import MCPServerConfig
from core.tools.base import ToolSpec

#: 暴露给 LLM 的函数名只允许这些字符（OpenAI function name 约束）
_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


def _normalize(name: str) -> str:
    """把任意名字收敛成合法的函数名片段。"""
    return _NAME_SAFE.sub("_", name).strip("_") or "unnamed"


def exposed_tool_name(server_name: str, tool_name: str) -> str:
    """生成暴露给 LLM 的唯一工具名：``<服务器名>__<原始工具名>``。"""
    return f"{_normalize(server_name)}__{_normalize(tool_name)}"


async def discover_mcp_tool_specs(
    servers: list[MCPServerConfig],
) -> tuple[list[ToolSpec], list[str]]:
    """连接各 MCP Server、发现工具并返回适配好的 ToolSpec 列表。

    返回 ``(工具列表, 警告列表)``；某个 Server 连不上或不支持的协议只产生警告，
    不会抛异常，从而保证本地工具与其他 Server 不受影响。
    """
    specs: list[ToolSpec] = []
    warnings: list[str] = []
    used_names: set[str] = set()

    for server in servers:
        if server.transport != "streamable_http":
            warnings.append(
                f"跳过 MCP Server {server.name!r}：暂不支持协议 {server.transport!r}"
            )
            continue

        try:
            mcp_tools = await list_server_tools(server)
        except Exception as exc:  # 单个 Server 故障隔离
            warnings.append(f"无法连接 MCP Server {server.name!r}，已跳过：{exc}")
            continue

        if not mcp_tools:
            warnings.append(f"MCP Server {server.name!r} 没有提供任何工具")
            continue

        for tool in mcp_tools:
            exposed = exposed_tool_name(server.name, tool.name)
            # 防止极少数规范化后仍撞名：追加序号
            if exposed in used_names:
                suffix = 2
                while f"{exposed}_{suffix}" in used_names:
                    suffix += 1
                exposed = f"{exposed}_{suffix}"
            used_names.add(exposed)

            handler = _make_handler(server, tool.name)
            specs.append(
                ToolSpec(
                    name=exposed,
                    description=_describe(server, tool),
                    parameters=dict(tool.input_schema or {"type": "object", "properties": {}}),
                    handler=handler,
                )
            )

        warnings.append(
            f"MCP Server {server.name!r}：已加载 {len(mcp_tools)} 个外部工具"
        )

    return specs, warnings


def _describe(server: MCPServerConfig, tool: Any) -> str:
    """给模型看的工具描述，附带来源服务器。"""
    desc = (tool.description or tool.name).strip()
    return f"[来自 MCP Server: {server.name}] {desc}"


def _make_handler(server: MCPServerConfig, tool_name: str) -> Callable[..., Awaitable[str]]:
    """构造一个异步 handler：按映射转发到指定 MCP Server 的指定工具。"""

    async def handler(**arguments: Any) -> str:
        return await call_server_tool(server, tool_name, arguments)

    return handler


__all__ = ["discover_mcp_tool_specs", "exposed_tool_name"]
