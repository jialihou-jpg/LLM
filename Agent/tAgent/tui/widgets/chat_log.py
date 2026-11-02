"""对话区组件。"""

from __future__ import annotations

import json
from typing import Any

from rich.markdown import Markdown as RichMarkdown
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static


class UserMessage(Static):
    """用户消息气泡。"""

    def __init__(self, content: str) -> None:
        text = Text()
        text.append("你", style="bold cyan")
        text.append("  ")
        text.append(content)
        super().__init__(text, classes="message user-message")


class AssistantMessage(Static):
    """助手消息气泡，支持流式刷新。

    使用 Rich 的 Markdown 渲染器而非 Textual 的 Markdown 组件：
    前者可以在同步调用中直接替换内容，不会与组件挂载过程产生竞态。
    """

    def __init__(self, content: str = "") -> None:
        super().__init__(RichMarkdown(content), classes="message assistant-message")
        self._markdown_text = content

    def set_markdown(self, content: str) -> None:
        """更新消息内容。"""
        self._markdown_text = content
        self.update(RichMarkdown(content))

    @property
    def content(self) -> str:
        return self._markdown_text


class ToolCallPanel(Static):
    """工具调用面板：展示工具名、参数与执行结果。"""

    def __init__(self, name: str, arguments: dict[str, Any] | None = None) -> None:
        tool_name = name
        tool_arguments = dict(arguments or {})
        text = self._build_text(tool_name, tool_arguments, None)
        super().__init__(text, classes="message tool-message")
        self._tool_name = tool_name
        self._tool_arguments = tool_arguments
        self._text = text

    def update_result(self, result: str, ok: bool = True) -> None:
        """回填工具执行结果。"""
        text = self._build_text(self._tool_name, self._tool_arguments, result, ok)
        self._text = text
        self.update(text)

    @property
    def plain_text(self) -> str:
        """面板的纯文本内容（便于测试与调试）。"""
        return self._text.plain

    @staticmethod
    def _build_text(
        name: str,
        arguments: dict[str, Any],
        result: str | None,
        ok: bool = True,
    ) -> Text:
        text = Text()
        text.append("工具 ", style="bold yellow")
        text.append(name, style="bold")
        if arguments:
            text.append("\n参数 ")
            text.append(
                json.dumps(arguments, ensure_ascii=False),
                style="italic",
            )
        if result is not None:
            text.append("\n结果 ")
            text.append(result, style="green" if ok else "bold red")
        return text


class ChatLog(VerticalScroll):
    """对话记录容器。"""

    def _append(self, widget: Static) -> None:
        self.mount(widget)
        self.call_after_refresh(self.scroll_end, animate=False)

    # ------------------------------------------------------------------ 消息
    def add_user(self, content: str) -> None:
        """追加一条用户消息。"""
        self._append(UserMessage(content))

    def add_assistant(self, content: str = "") -> AssistantMessage:
        """追加一个助手气泡，返回该组件用于流式更新。"""
        widget = AssistantMessage(content)
        self._append(widget)
        return widget

    def update_assistant(self, widget: AssistantMessage, text: str) -> None:
        """更新助手气泡内容。"""
        widget.set_markdown(text)

    def add_tool_call(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> ToolCallPanel:
        """追加一个工具调用面板。"""
        panel = ToolCallPanel(name, arguments)
        self._append(panel)
        return panel

    def update_tool_call(self, panel: ToolCallPanel, result: str, ok: bool = True) -> None:
        """回填工具调用结果。"""
        panel.update_result(result, ok)

    def add_error(self, content: str) -> None:
        """追加一条错误提示。"""
        self._append(Static(Text(content, style="bold red"), classes="message error-message"))

    def add_info(self, content: str) -> None:
        """追加一条灰色提示信息。"""
        self._append(Static(Text(content, style="dim"), classes="info-message"))

    def clear(self) -> None:
        """清空对话记录。"""
        self.remove_children()
