"""LLM 相关的类型定义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LLMEvent:
    """流式响应中的事件基类。"""


@dataclass(slots=True)
class ContentDelta(LLMEvent):
    """回答文本增量。"""

    text: str = ""


@dataclass(slots=True)
class ToolCallDelta(LLMEvent):
    """工具调用增量。

    ``index`` 用于把同一轮回复中的多个工具调用区分开（OpenAI 兼容协议约定）。
    """

    index: int = 0
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass(slots=True)
class FinishReason(LLMEvent):
    """模型给出的结束原因。"""

    reason: str = ""


@dataclass(slots=True)
class Usage(LLMEvent):
    """token 用量（部分服务商不会返回）。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


__all__ = ["ContentDelta", "FinishReason", "LLMEvent", "ToolCallDelta", "Usage"]
