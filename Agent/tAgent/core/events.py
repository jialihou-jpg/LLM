"""核心层对外抛出的事件。

Agent 的行为用"事件流"描述：核心层不关心事件如何展示，
只负责按顺序产出事件；各前端（TUI / Web / Desktop / Mobile）
自行决定如何渲染这些事件。

事件继承自 :class:`AgentEvent`，新增事件时保持向后兼容即可。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentEvent:
    """所有事件的基类（标记类型，便于前端统一 isinstance 判断）。"""


@dataclass(slots=True)
class RunStarted(AgentEvent):
    """一次提问处理开始。"""

    user_input: str = ""


@dataclass(slots=True)
class AssistantDelta(AgentEvent):
    """助手回答的增量文本（流式）。"""

    text: str = ""


@dataclass(slots=True)
class AssistantCompleted(AgentEvent):
    """助手回答完成。"""

    text: str = ""


@dataclass(slots=True)
class ToolCallStarted(AgentEvent):
    """开始调用工具。"""

    call_id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallCompleted(AgentEvent):
    """工具调用结束。"""

    call_id: str = ""
    name: str = ""
    result: str = ""
    ok: bool = True


@dataclass(slots=True)
class ErrorRaised(AgentEvent):
    """本轮处理出现错误。"""

    message: str = ""
    detail: str = ""


@dataclass(slots=True)
class RunCompleted(AgentEvent):
    """一次提问处理结束。"""

    rounds: int = 0
    success: bool = True


__all__ = [
    "AgentEvent",
    "AssistantCompleted",
    "AssistantDelta",
    "ErrorRaised",
    "RunCompleted",
    "RunStarted",
    "ToolCallCompleted",
    "ToolCallStarted",
]
