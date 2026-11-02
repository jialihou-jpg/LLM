"""MCP Client 的离线测试（不连接真实服务器）。

覆盖：.mcp.json 解析、工具名规范化与前缀、跨服务器工具名冲突、单个 Server
故障隔离、结果格式化（文本 / 错误）、以及 handler 按映射转发到对应 Server。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from core.mcp import (
    MCPServerConfig,
    discover_mcp_tool_specs,
    exposed_tool_name,
    load_mcp_servers,
)
from core.mcp.client import _format_result
from core.tools.registry import ToolRegistry


# ------------------------------------------------------------------ 配置解析
def test_load_mcp_servers_parses_mcp_servertag(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "Bazi-MCP": {
                        "type": "streamable_http",
                        "url": "https://example.com/mcp",
                        "headers": {"Authorization": "Bearer xyz"},
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    servers, warnings = load_mcp_servers(tmp_path)
    assert warnings == []
    assert len(servers) == 1
    server = servers[0]
    assert server.name == "Bazi-MCP"
    assert server.url == "https://example.com/mcp"
    assert server.transport == "streamable_http"
    assert server.headers == {"Authorization": "Bearer xyz"}


def test_load_mcp_servers_missing_file_returns_empty(tmp_path):
    servers, warnings = load_mcp_servers(tmp_path)
    assert servers == []
    assert warnings == []


def test_load_mcp_servers_skips_entry_without_url(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {"mcpServers": {"NoUrl": {"type": "streamable_http"}, "Good": {"url": "https://x/mcp"}}}
        ),
        encoding="utf-8",
    )
    servers, warnings = load_mcp_servers(tmp_path)
    assert [s.name for s in servers] == ["Good"]
    assert any("NoUrl" in w for w in warnings)


# ------------------------------------------------------------------ 命名
def test_exposed_tool_name_prefixes_server():
    # 合法字符（含连字符）保留，仅替换非法字符
    assert exposed_tool_name("Bazi-MCP", "calcBazi") == "Bazi-MCP__calcBazi"


def test_exposed_tool_name_sanitizes_bad_chars():
    assert exposed_tool_name("my server!", "do thing") == "my_server__do_thing"


# ------------------------------------------------------------------ 发现与适配
def _fake_tool(name: str, desc: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=desc or f"desc of {name}",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )


def test_discover_registers_prefixed_tools(monkeypatch):
    calls: list[str] = []

    async def fake_list(server):
        calls.append(server.name)
        return [_fake_tool("calcBazi"), _fake_tool("fortune")]

    monkeypatch.setattr("core.mcp.discovery.list_server_tools", fake_list)
    server = MCPServerConfig(name="Bazi-MCP", url="https://x/mcp")
    specs, warnings = asyncio.run(discover_mcp_tool_specs([server]))

    assert calls == ["Bazi-MCP"]
    names = {s.name for s in specs}
    assert names == {"Bazi-MCP__calcBazi", "Bazi-MCP__fortune"}
    # 描述带来源标注
    assert all(s.description.startswith("[来自 MCP Server: Bazi-MCP]") for s in specs)
    assert any("已加载 2 个外部工具" in w for w in warnings)


def test_discover_isolates_dead_server(monkeypatch):
    async def boom(server):
        raise ConnectionError("refused")

    async def good(server):
        return [_fake_tool("ok")]

    monkeypatch.setattr("core.mcp.discovery.list_server_tools", boom)
    dead = MCPServerConfig(name="Dead", url="https://dead/mcp")
    alive = MCPServerConfig(name="Alive", url="https://alive/mcp")

    # 第一次调用（只发现 dead）会失败；改写成按服务器返回
    async def router(server):
        if server.name == "Alive":
            return [_fake_tool("ok")]
        raise ConnectionError("refused")

    monkeypatch.setattr("core.mcp.discovery.list_server_tools", router)
    specs, warnings = asyncio.run(discover_mcp_tool_specs([dead, alive]))

    # 即使 dead 连不上，alive 的工具仍然注册成功
    assert [s.name for s in specs] == ["Alive__ok"]
    assert any("Dead" in w and "已跳过" in w for w in warnings)


def test_discover_skips_unsupported_transport():
    server = MCPServerConfig(name="S", url="https://x", transport="stdio")
    specs, warnings = asyncio.run(discover_mcp_tool_specs([server]))
    assert specs == []
    assert any("暂不支持协议" in w for w in warnings)


# ------------------------------------------------------------------ 调用转发与结果
def test_handler_forwards_to_right_server(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_call(server, tool_name, arguments):
        seen["server"] = server.name
        seen["tool"] = tool_name
        seen["args"] = arguments
        return "RESULT-123"

    monkeypatch.setattr("core.mcp.discovery.call_server_tool", fake_call)
    server = MCPServerConfig(name="Bazi-MCP", url="https://x/mcp")

    async def fake_list(s):
        return [_fake_tool("calcBazi")]

    monkeypatch.setattr("core.mcp.discovery.list_server_tools", fake_list)
    specs, _ = asyncio.run(discover_mcp_tool_specs([server]))

    registry = ToolRegistry(specs)
    result = asyncio.run(registry.acall("Bazi-MCP__calcBazi", {"q": "2024"}))

    assert result.ok
    assert result.output == "RESULT-123"
    assert seen == {"server": "Bazi-MCP", "tool": "calcBazi", "args": {"q": "2024"}}


def test_format_result_extracts_text():
    result = SimpleNamespace(
        content=[SimpleNamespace(text="hello "), SimpleNamespace(text="world")],
        isError=False,
    )
    assert _format_result(result) == "hello \nworld"


def test_format_result_handles_error():
    result = SimpleNamespace(
        content=[SimpleNamespace(text="boom")],
        is_error=True,
    )
    assert _format_result(result) == "MCP 工具执行返回错误：boom"
