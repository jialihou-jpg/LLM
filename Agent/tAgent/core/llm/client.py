"""LLM 客户端抽象。

核心层只依赖本协议，因此可以在不改业务代码的前提下替换成
本地模型、其他云服务商或测试用的假客户端。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol, runtime_checkable

from core.llm.types import LLMEvent
from core.models import Message


@runtime_checkable
class LLMClient(Protocol):
    """流式对话客户端协议。"""

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """发起一次流式对话，逐个产出事件。"""
        ...

    async def aclose(self) -> None:
        """释放底层资源。"""
        ...


__all__ = ["LLMClient"]
