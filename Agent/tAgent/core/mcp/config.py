"""MCP Server 配置读取。

约定：tAgent 启动时从**当前项目目录**（默认进程启动工作目录 ``Path.cwd()``，
即你运行 ``python -m tui`` 时所在的目录，而不是 tAgent 源码目录）下读取
``.mcp.json``，获得外部 MCP Server 的连接信息。

文件格式（与 Claude / Cursor 等工具的 ``mcpServers`` 约定一致）：

.. code-block:: json

    {
      "mcpServers": {
        "Bazi-MCP": {
          "type": "streamable_http",
          "url": "https://example.com/mcp",
          "headers": {"Authorization": "Bearer ..."}
        }
      }
    }

本模块只做同步的配置解析，不发起任何网络连接（网络连接在 :mod:`core.mcp.client`）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

MCP_CONFIG_FILENAME = ".mcp.json"


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """一个外部 MCP Server 的连接配置。"""

    name: str
    url: str
    transport: str = "streamable_http"
    headers: dict[str, str] = field(default_factory=dict)


def find_mcp_config(project_root: str | os.PathLike[str] | None = None) -> Path | None:
    """定位 ``.mcp.json``；不存在时返回 ``None``（不报错，视为没有外部 MCP）。"""
    root = Path(project_root) if project_root is not None else Path.cwd()
    candidate = root / MCP_CONFIG_FILENAME
    return candidate if candidate.is_file() else None


def load_mcp_servers(
    project_root: str | os.PathLike[str] | None = None,
) -> tuple[list[MCPServerConfig], list[str]]:
    """读取 ``.mcp.json``，返回 (MCP Server 配置列表, 跳过原因列表)。

    文件不存在时返回空列表（没有外部 MCP，不算错误）；某个条目缺少 ``url``
    或格式错误时不会让整体失败，而是记入 ``warnings`` 后跳过。
    """
    path = find_mcp_config(project_root)
    if path is None:
        return [], []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"无法读取 {path}：{exc}"]

    servers_raw = raw.get("mcpServers") or {}
    if not isinstance(servers_raw, dict):
        return [], [f"{path} 的 mcpServers 必须是对象"]

    servers: list[MCPServerConfig] = []
    warnings: list[str] = []
    for name, spec in servers_raw.items():
        if not isinstance(spec, dict):
            warnings.append(f"跳过 MCP Server {name!r}：配置不是对象")
            continue
        url = spec.get("url") or spec.get("serverUrl")
        if not url:
            warnings.append(f"跳过 MCP Server {name!r}：缺少 url")
            continue
        transport = spec.get("type") or spec.get("transport") or "streamable_http"
        headers = spec.get("headers") or {}
        if not isinstance(headers, dict):
            headers = {}
        servers.append(
            MCPServerConfig(
                name=str(name),
                url=str(url),
                transport=str(transport),
                headers={str(k): str(v) for k, v in headers.items()},
            )
        )
    return servers, warnings


__all__ = [
    "MCP_CONFIG_FILENAME",
    "MCPServerConfig",
    "find_mcp_config",
    "load_mcp_servers",
]
