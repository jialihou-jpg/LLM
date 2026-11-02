"""工具抽象。

一个工具由三部分组成：名字、描述、参数 JSON Schema，以及真正的执行函数。
核心层通过 :class:`ToolSpec` 把它们打包在一起，注册中心再转换成
OpenAI 兼容的 ``tools`` 声明。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

ToolHandler = Callable[..., str | Awaitable[str]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """工具声明。"""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None

    def to_schema(self) -> dict[str, Any]:
        """转换为 OpenAI 兼容的工具声明结构。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


@dataclass(slots=True)
class ToolResult:
    """工具执行结果。"""

    ok: bool = True
    output: str = ""
    error: str = ""

    @classmethod
    def success(cls, output: str) -> ToolResult:
        return cls(ok=True, output=output)

    @classmethod
    def failure(cls, error: str) -> ToolResult:
        return cls(ok=False, output="", error=error)


__all__ = ["ToolHandler", "ToolResult", "ToolSpec"]
