"""OpenAI 兼容协议客户端（支持 SSE 流式响应）。

对大多数提供 OpenAI 兼容接口的服务商（OpenAI、SiliconFlow、通义、DeepSeek 等）
只需替换 ``base_url`` / ``model`` 即可复用。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from core.errors import LLMError
from core.llm.types import (
    ContentDelta,
    FinishReason,
    LLMEvent,
    ToolCallDelta,
    Usage,
)
from core.models import Message, messages_to_wire

DATA_PREFIX = "data:"
DONE_MARKER = "[DONE]"


class OpenAICompatibleClient:
    """基于 httpx 的异步流式客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._extra_headers = extra_headers or {}

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        headers.update(self._extra_headers)
        return headers

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """发起一次流式对话请求。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages_to_wire(messages),
            "stream": True,
        }
        if tools:
            payload["tools"] = list(tools)

        try:
            async with self._client.stream(
                "POST",
                self.chat_completions_url,
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", "replace")[:500]
                    raise LLMError(f"模型服务返回 {response.status_code}：{detail}")
                async for event in self._iter_events(response):
                    yield event
        except httpx.HTTPError as exc:
            detail = str(exc) or "连接中断或超时"
            raise LLMError(f"请求模型服务失败（{type(exc).__name__}）：{detail}") from exc
        except LLMError:
            raise
        except Exception as exc:  # pragma: no cover - 兜底保护
            raise LLMError(f"请求模型服务时发生未知错误：{exc}") from exc

    async def _iter_events(self, response: httpx.Response) -> AsyncIterator[LLMEvent]:
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line or not line.startswith(DATA_PREFIX):
                    continue
                data = line[len(DATA_PREFIX):].strip()
                if data == DONE_MARKER:
                    return
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for event in self._parse_payload(payload):
                    yield event

    def _parse_payload(self, payload: dict[str, Any]) -> list[LLMEvent]:
        events: list[LLMEvent] = []
        usage = payload.get("usage")
        if isinstance(usage, dict):
            events.append(
                Usage(
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    total_tokens=int(usage.get("total_tokens") or 0),
                )
            )

        for choice in payload.get("choices") or []:
            finish_reason = choice.get("finish_reason")
            if finish_reason:
                events.append(FinishReason(reason=str(finish_reason)))
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                events.append(ContentDelta(text=str(content)))
            for raw_call in delta.get("tool_calls") or []:
                function = raw_call.get("function") or {}
                events.append(
                    ToolCallDelta(
                        index=int(raw_call.get("index") or 0),
                        id=str(raw_call.get("id") or ""),
                        name=str(function.get("name") or ""),
                        arguments=str(function.get("arguments") or ""),
                    )
                )
        return events

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> OpenAICompatibleClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


__all__ = ["OpenAICompatibleClient"]
