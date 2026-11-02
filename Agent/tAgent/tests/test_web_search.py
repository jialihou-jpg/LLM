"""百度千帆 AI 搜索（网页搜索）工具的离线测试（不发起真实网络请求）。"""

from __future__ import annotations

import asyncio
import json

import httpx

from core.config import SearchSettings
from core.tools.builtin.web_search import (
    SEARCH_TOOL_NAME,
    _truncate_query,
    build_search_tools,
)
from core.tools.registry import ToolRegistry

ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"


def make_registry(
    settings: SearchSettings,
    handler: httpx.MockTransport,
) -> tuple[ToolRegistry, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler)
    return ToolRegistry(build_search_tools(settings, client=client)), client


def call(registry: ToolRegistry, **arguments: object):
    return asyncio.run(registry.acall(SEARCH_TOOL_NAME, arguments))


def test_search_formats_references() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == ENDPOINT
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["messages"] == [{"role": "user", "content": "北京天气"}]
        assert body["search_source"] == "baidu_search_v2"
        assert body["edition"] == "standard"
        assert body["resource_type_filter"] == [{"type": "web", "top_k": 5}]
        # 纯搜索接口不应携带模型相关参数
        assert "model" not in body
        assert "stream" not in body
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "references": [
                    {
                        "id": 1,
                        "title": "示例天气网",
                        "web_anchor": "示例天气网",
                        "url": "https://example.com/weather",
                        "snippet": "今天晴，20℃，适合出行。",
                        "date": "2026-10-26",
                        "type": "web",
                    }
                ],
            },
        )

    settings = SearchSettings(api_key="test-key", top_k=5, timeout=5.0)
    registry, client = make_registry(settings, httpx.MockTransport(handler))
    try:
        result = call(registry, query="北京天气")
    finally:
        asyncio.run(client.aclose())

    assert result.ok is True
    assert "搜索结果（共 1 条" in result.output
    assert "示例天气网" in result.output
    assert "2026-10-26" in result.output
    assert "https://example.com/weather" in result.output
    assert "今天晴，20℃" in result.output


def test_search_uses_configured_edition() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["edition"] == "turbo"
        return httpx.Response(
            200,
            json={
                "references": [
                    {"id": 1, "title": "t", "url": "https://example.com", "content": "c"}
                ]
            },
        )

    settings = SearchSettings(api_key="test-key", edition="turbo")
    registry, client = make_registry(settings, httpx.MockTransport(handler))
    try:
        result = call(registry, query="test")
    finally:
        asyncio.run(client.aclose())

    assert result.ok is True


def test_missing_api_key_returns_clear_error() -> None:
    registry = ToolRegistry(build_search_tools(SearchSettings()))
    result = call(registry, query="北京天气")

    assert result.ok is False
    assert "API Key" in result.error
    assert "[search]" in result.error


def test_missing_query_returns_clear_error() -> None:
    registry = ToolRegistry(build_search_tools(SearchSettings(api_key="test-key")))
    result = call(registry)

    assert result.ok is False
    assert "缺少参数 query" in result.error


def test_http_error_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 216003, "message": "Authentication error"})

    registry, client = make_registry(
        SearchSettings(api_key="bad-key"), httpx.MockTransport(handler)
    )
    try:
        result = call(registry, query="test")
    finally:
        asyncio.run(client.aclose())

    assert result.ok is False
    assert "HTTP 401" in result.error
    assert "Authentication error" in result.error


def test_api_error_in_success_response_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 400, "message": "quota exceeded"})

    registry, client = make_registry(
        SearchSettings(api_key="test-key"), httpx.MockTransport(handler)
    )
    try:
        result = call(registry, query="test")
    finally:
        asyncio.run(client.aclose())

    assert result.ok is False
    assert "code=400" in result.error
    assert "quota exceeded" in result.error


def test_empty_result_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"request_id": "req-2", "references": []})

    registry, client = make_registry(
        SearchSettings(api_key="test-key"), httpx.MockTransport(handler)
    )
    try:
        result = call(registry, query="test")
    finally:
        asyncio.run(client.aclose())

    assert result.ok is False
    assert "未返回任何结果" in result.error


def test_network_error_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    registry, client = make_registry(
        SearchSettings(api_key="test-key"), httpx.MockTransport(handler)
    )
    try:
        result = call(registry, query="test")
    finally:
        asyncio.run(client.aclose())

    assert result.ok is False
    assert "网络请求失败" in result.error


def test_timeout_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    registry, client = make_registry(
        SearchSettings(api_key="test-key"), httpx.MockTransport(handler)
    )
    try:
        result = call(registry, query="test")
    finally:
        asyncio.run(client.aclose())

    assert result.ok is False
    assert "超时" in result.error


def test_truncate_query_counts_chinese_as_two() -> None:
    # 36 个汉字权重恰好 72，不应截断
    assert _truncate_query("字" * 36) == "字" * 36
    # 37 个汉字只保留前 36 个
    assert _truncate_query("字" * 37) == "字" * 36
    # 72 个 ASCII 字符不截断，73 个截到 72
    assert _truncate_query("a" * 72) == "a" * 72
    assert _truncate_query("a" * 73) == "a" * 72
    # 混合：1 个汉字（权重 2）+ 70 个 ASCII（权重 70）= 72
    assert _truncate_query("字" + "a" * 70 + "字") == "字" + "a" * 70
