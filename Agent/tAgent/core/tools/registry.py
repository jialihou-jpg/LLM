"""工具注册中心。

职责：
- 保存工具声明（:class:`ToolSpec`）
- 生成发给模型服务的 ``tools`` 结构
- 校验并调用工具，把异常统一转换为可回传给模型的错误文本
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Sequence
from typing import Any

from core.tools.base import ToolResult, ToolSpec

JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
}


class ToolRegistry:
    """工具集合。"""

    def __init__(self, tools: Iterable[ToolSpec] = ()) -> None:
        self._tools: dict[str, ToolSpec] = {}
        for tool in tools:
            self.register(tool)

    # ------------------------------------------------------------------ 注册
    def register(self, tool: ToolSpec) -> ToolSpec:
        """注册（或覆盖）一个工具。"""
        if not tool.name:
            raise ValueError("工具名称不能为空")
        self._tools[tool.name] = tool
        return tool

    def register_function(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Any,
    ) -> ToolSpec:
        """以函数形式注册工具（便捷方法）。"""
        return self.register(
            ToolSpec(name=name, description=description, parameters=parameters, handler=handler)
        )

    # ------------------------------------------------------------------ 查询
    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        """生成 OpenAI 兼容的 tools 声明列表。"""
        return [tool.to_schema() for tool in self._tools.values()]

    # ------------------------------------------------------------------ 调用
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """同步执行工具；任何异常都会被转换成失败结果，而不是向上抛出。"""
        tool, payload, failure = self._prepare(name, arguments)
        if failure is not None:
            return failure
        assert tool is not None and tool.handler is not None

        try:
            output = tool.handler(**payload)
        except Exception as exc:  # 工具异常统一转成文本回传给模型
            return ToolResult.failure(f"工具执行出错：{exc}")
        if inspect.isawaitable(output):
            return ToolResult.failure(f"工具 {name} 是异步工具，请使用 acall()")
        return ToolResult.success(str(output))

    async def acall(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """异步执行工具，同时兼容同步与异步处理器。

        异步处理器（例如网络搜索）不会阻塞事件循环；同步处理器保持原有行为。
        """
        tool, payload, failure = self._prepare(name, arguments)
        if failure is not None:
            return failure
        assert tool is not None and tool.handler is not None

        try:
            output = tool.handler(**payload)
            if inspect.isawaitable(output):
                output = await output
        except Exception as exc:  # 工具异常统一转成文本回传给模型
            return ToolResult.failure(f"工具执行出错：{exc}")
        return ToolResult.success(str(output))

    def _prepare(
        self, name: str, arguments: dict[str, Any] | None
    ) -> tuple[ToolSpec | None, dict[str, Any], ToolResult | None]:
        """查找并校验工具，返回 (工具, 校验后的参数, 失败结果)。"""
        tool = self._tools.get(name)
        if tool is None:
            return None, {}, ToolResult.failure(f"未知的工具：{name}")
        if tool.handler is None:
            return None, {}, ToolResult.failure(f"工具 {name} 没有绑定执行函数")

        payload = dict(arguments or {})
        error = self.validate(tool, payload)
        if error:
            return None, {}, ToolResult.failure(error)
        return tool, payload, None

    def validate(self, tool: ToolSpec, arguments: dict[str, Any]) -> str:
        """校验参数，返回错误描述（为空表示校验通过）。"""
        schema = tool.parameters or {}
        properties: dict[str, Any] = schema.get("properties") or {}
        required: Sequence[str] = schema.get("required") or []

        for key in required:
            if arguments.get(key) in (None, ""):
                return f"缺少参数 {key}"

        for key, value in list(arguments.items()):
            if key not in properties:
                arguments.pop(key)
                continue
            coerced = self._coerce(properties[key], value)
            if coerced is _INVALID:
                return f"参数 {key} 类型不正确"
            arguments[key] = coerced
        return ""

    @staticmethod
    def _coerce(spec: dict[str, Any], value: Any) -> Any:
        expected = spec.get("type")
        if not expected or value is None:
            return value
        allowed = JSON_TYPES.get(str(expected), ())
        if not allowed:
            return value
        if isinstance(value, bool) and bool not in allowed:
            return _INVALID
        if isinstance(value, allowed):
            return value
        if isinstance(value, str):
            text = value.strip()
            if expected == "integer":
                try:
                    return int(text)
                except ValueError:
                    return _INVALID
            if expected == "number":
                try:
                    return float(text)
                except ValueError:
                    return _INVALID
            if expected == "boolean":
                lowered = text.lower()
                if lowered in ("true", "1", "yes"):
                    return True
                if lowered in ("false", "0", "no"):
                    return False
                return _INVALID
            if expected == "string":
                return text
        return _INVALID


class _Invalid:
    """类型校验失败的哨兵值。"""

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return "<invalid>"


_INVALID = _Invalid()


__all__ = ["ToolRegistry"]
