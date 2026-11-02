"""测试替身：可编排的假 LLM 客户端。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from core.llm.types import ContentDelta, ToolCallDelta, Usage
from core.models import Message


class FakeLLMClient:
    """按脚本产出事件的假客户端。

    ``scripts`` 中每一项对应一次模型请求，返回该次请求应产出的事件列表。
    """

    def __init__(self, scripts: list[list[Any]]) -> None:
        self.scripts = list(scripts)
        self.calls: list[list[dict[str, Any]]] = []
        self.closed = False

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Any]:
        self.calls.append([message.to_dict() for message in messages])
        if not self.scripts:
            return
        events = self.scripts.pop(0)
        for event in events:
            yield event

    async def aclose(self) -> None:
        self.closed = True

def text_events(*chunks: str) -> list[Any]:
    """构造纯文本增量事件。"""
    return [ContentDelta(text=chunk) for chunk in chunks]


def tool_events(name: str, arguments: str, call_id: str = "call-1") -> list[Any]:
    """构造一次工具调用事件。"""
    return [
        ToolCallDelta(index=0, id=call_id, name=name, arguments=arguments),
    ]


def usage(prompt: int = 10, completion: int = 5) -> Usage:
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )
