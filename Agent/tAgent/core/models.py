"""核心领域模型：消息与工具调用。

这些对象是核心层的"通用语言"，前端与后端都基于它们交换数据，
并且可直接序列化为 OpenAI 兼容的 chat/completions 报文。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ToolCall:
    """一次工具调用请求。

    ``arguments`` 保留模型返回的原始 JSON 文本，交由工具注册中心统一解析，
    这样可以避免在流式拼接过程中因为 JSON 不完整而崩溃。
    """

    id: str = ""
    name: str = ""
    arguments: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为 OpenAI 兼容的工具调用结构。"""
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCall:
        """从 OpenAI 兼容结构还原。"""
        function = data.get("function") or {}
        return cls(
            id=str(data.get("id") or ""),
            name=str(function.get("name") or ""),
            arguments=str(function.get("arguments") or ""),
        )

    def __str__(self) -> str:  # pragma: no cover - 仅用于调试输出
        return f"ToolCall(name={self.name!r}, id={self.id!r})"


@dataclass(slots=True)
class Message:
    """一条对话消息。"""

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为可发送的请求体结构。"""
        payload: dict[str, Any] = {"role": self.role, "content": self.content or None}
        if self.tool_calls:
            payload["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.name:
            payload["name"] = self.name
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """从请求体结构还原。"""
        tool_calls = [ToolCall.from_dict(item) for item in data.get("tool_calls") or []]
        return cls(
            role=data.get("role", "user"),
            content=data.get("content") or "",
            tool_calls=tool_calls,
            tool_call_id=str(data.get("tool_call_id") or ""),
            name=str(data.get("name") or ""),
        )

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def assistant(
        cls, content: str = "", tool_calls: Iterable[ToolCall] | None = None
    ) -> Message:
        return cls(role="assistant", content=content, tool_calls=list(tool_calls or []))


def messages_to_wire(messages: Iterable[Message]) -> list[dict[str, Any]]:
    """把消息列表转换成请求体结构。"""
    return [message.to_dict() for message in messages]
