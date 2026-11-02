"""对话会话（会话状态）。

``Session`` 只负责"消息历史"这一份状态，Agent 负责"行为"。
两者分离后，Web 前端可以为每个用户维护一个 Session，
TUI 前端则通常在整个进程生命周期内复用同一个 Session。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.models import Message, ToolCall


class Session:
    """一条有序的消息历史。"""

    def __init__(self, system_prompt: str = "", session_id: str = "") -> None:
        self.session_id = session_id
        self._messages: list[Message] = []
        if system_prompt:
            self._messages.append(Message.system(system_prompt))

    # ------------------------------------------------------------------ 读取
    @property
    def messages(self) -> list[Message]:
        """消息列表的浅拷贝，外部修改不会影响会话状态。"""
        return list(self._messages)

    @property
    def system_prompt(self) -> str:
        for message in self._messages:
            if message.role == "system":
                return message.content
        return ""

    def to_wire(self) -> list[dict[str, Any]]:
        """转换为发送给模型服务的请求体结构。"""
        return [message.to_dict() for message in self._messages]

    # ------------------------------------------------------------------ 写入
    def add_message(self, message: Message) -> Message:
        self._messages.append(message)
        return message

    def add_user(self, content: str) -> Message:
        return self.add_message(Message.user(content))

    def add_assistant(
        self, content: str = "", tool_calls: Iterable[ToolCall] | None = None
    ) -> Message:
        return self.add_message(Message.assistant(content, tool_calls))

    def add_tool_result(self, tool_call_id: str, content: str, name: str = "") -> Message:
        return self.add_message(
            Message(
                role="tool",
                content=content,
                tool_call_id=tool_call_id,
                name=name,
            )
        )

    def reset(self, system_prompt: str | None = None) -> None:
        """清空历史（保留系统提示词，除非显式传入新的）。"""
        prompt = self.system_prompt if system_prompt is None else system_prompt
        self._messages.clear()
        if prompt:
            self._messages.append(Message.system(prompt))

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Session id={self.session_id!r} messages={len(self._messages)}>"
