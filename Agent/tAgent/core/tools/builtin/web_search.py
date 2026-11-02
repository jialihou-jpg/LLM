"""网络搜索工具：调用百度千帆「AI 搜索 - 网页搜索」API。

接口：``POST /v2/ai_search/web_search``。它只做全网检索并返回网页结果
（标题、摘要片段、发布日期、URL），**不调用大模型生成摘要**，因此不产生
模型 token 费用；每月有 1500 次免费额度（按天发放，优先抵扣免费资源）。

工具只依赖 ``core.config.SearchSettings``，API Key 由配置文件或环境变量提供，
不在代码中硬编码。任何失败都会转换成清晰的中文错误文本，由注册中心回传给模型。
"""

from __future__ import annotations

from typing import Any

import httpx

from core.config import SearchSettings
from core.tools.base import ToolSpec

SEARCH_TOOL_NAME = "searchweb"
# 接口要求 query 不超过 72 个"字符"（一个汉字按 2 计），超长只取前 72 检索
MAX_QUERY_WEIGHT = 72
# 每条网页结果回传给模型的摘要片段最大长度，避免占用过多上下文
MAX_SNIPPET_CHARS = 300


class SearchError(RuntimeError):
    """搜索失败；错误信息可直接回传给模型。"""


class WebSearchTool:
    """可被 :class:`ToolRegistry` 调用的异步搜索工具。"""

    def __init__(
        self,
        settings: SearchSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    async def __call__(self, query: str | None = None, **_: object) -> str:
        return await self.search(query)

    async def search(self, query: str | None) -> str:
        text = (query or "").strip()
        if not text:
            raise SearchError("缺少参数 query：请提供要搜索的关键词或问题")
        # 接口对超长 query 只检索前 72 个字符，这里提前截断，行为更可预期
        text = _truncate_query(text)

        api_key = (self._settings.api_key or "").strip()
        if not api_key:
            raise SearchError(
                "未配置百度千帆搜索 API Key，请在 config.ini 的 [search] 段设置 "
                "baidu_qianfan_api_key（兼容旧名 baidu_qianfan_key）"
            )

        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": text}],
            "search_source": "baidu_search_v2",
            "edition": self._settings.edition,
            "resource_type_filter": [{"type": "web", "top_k": self._settings.top_k}],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    self._settings.endpoint,
                    headers=headers,
                    json=payload,
                )
            else:
                timeout = httpx.Timeout(self._settings.timeout)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        self._settings.endpoint,
                        headers=headers,
                        json=payload,
                    )
        except httpx.TimeoutException as exc:
            raise SearchError(
                f"搜索请求超时（{self._settings.timeout:g} 秒），请稍后重试"
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchError(f"搜索网络请求失败：{exc or type(exc).__name__}") from exc

        if response.status_code >= 400:
            raise SearchError(_http_error_message(response))
        return _format_response(response)


def _truncate_query(text: str) -> str:
    """按接口规则截断 query：ASCII 字符计 1，其余字符（如汉字）计 2，上限 72。"""
    kept: list[str] = []
    weight = 0
    for char in text:
        char_weight = 1 if ord(char) < 128 else 2
        if weight + char_weight > MAX_QUERY_WEIGHT:
            break
        kept.append(char)
        weight += char_weight
    return "".join(kept)


def _safe_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("message", "error_msg", "msg"):
        value = payload.get(key)
        if value:
            return str(value).strip()
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "").strip()
    if error:
        return str(error).strip()
    return ""


def _http_error_message(response: httpx.Response) -> str:
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    detail = _safe_message(payload)
    if isinstance(payload, dict):
        code = payload.get("code")
        if code not in (None, "", 0, "0"):
            detail = f"code={code} {detail}".strip()
    if not detail:
        detail = (response.text or "").strip()[:300]
    return f"搜索 API 返回错误（HTTP {response.status_code}）：{detail or '无错误详情'}"


def _format_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchError("搜索 API 返回了无法解析的内容") from exc
    if not isinstance(payload, dict):
        raise SearchError("搜索 API 返回格式异常")

    code = payload.get("code")
    if code not in (None, "", 0, "0"):
        detail = _safe_message(payload) or "未知错误"
        raise SearchError(f"搜索 API 返回错误（code={code}）：{detail}")

    references = payload.get("references") or []
    result_lines: list[str] = []
    if isinstance(references, list):
        for reference in references:
            if not isinstance(reference, dict):
                continue
            url = str(reference.get("url") or "").strip()
            if not url:
                continue
            title = str(
                reference.get("title") or reference.get("web_anchor") or ""
            ).strip()
            title = title or "(无标题)"
            date = str(reference.get("date") or "").strip()
            snippet = str(
                reference.get("snippet") or reference.get("content") or ""
            ).strip()
            snippet = _clean_snippet(snippet)

            block = title + (f"（{date}）" if date else "") + f"\n   {url}"
            if snippet:
                block += f"\n   摘要：{snippet}"
            result_lines.append(block)

    if not result_lines:
        raise SearchError("搜索 API 未返回任何结果，请更换关键词后重试")

    header = f"搜索结果（共 {len(result_lines)} 条，按相关度排序）："
    numbered = [f"{index}. {line}" for index, line in enumerate(result_lines, 1)]
    return header + "\n\n" + "\n\n".join(numbered)


def _clean_snippet(text: str) -> str:
    """清理摘要里的控制字符，并限制单条长度。"""
    cleaned = " ".join(text.split())
    if len(cleaned) <= MAX_SNIPPET_CHARS:
        return cleaned
    return cleaned[:MAX_SNIPPET_CHARS] + "……"


def build_search_tools(
    settings: SearchSettings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[ToolSpec]:
    """构造网络搜索工具声明。

    即使没有配置 API Key 也会返回工具声明，调用时会得到明确的配置错误，
    便于模型向用户说明原因。
    """
    tool = WebSearchTool(settings or SearchSettings(), client=client)
    return [
        ToolSpec(
            name=SEARCH_TOOL_NAME,
            description=(
                "联网搜索工具。当需要获取最新信息、实时新闻、当前事件或"
                "训练数据之外的资料时使用；输入搜索关键词或问题，"
                "返回按相关度排序的网页结果（标题、发布日期、URL 与摘要片段），"
                "可结合摘要片段与 fetchweb 阅读原文后回答用户"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或完整问题，例如“2026年诺贝尔物理学奖”",
                    }
                },
                "required": ["query"],
            },
            handler=tool,
        )
    ]


__all__ = [
    "SEARCH_TOOL_NAME",
    "SearchError",
    "WebSearchTool",
    "build_search_tools",
]
