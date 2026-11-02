"""输入框组件。"""

from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import TextArea


class PromptInput(TextArea):
    """多行输入框。

    - ``Enter``：发送
    - ``Shift+Enter`` / ``Alt+Enter``：换行
    """

    BINDINGS = [
        Binding("enter", "submit", "发送", priority=True),
        Binding("shift+enter", "newline", "换行", priority=True),
        Binding("alt+enter", "newline", "换行", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    PromptInput {
        height: 5;
        border: tall $accent;
    }
    """

    class Submitted(Message):
        """用户提交了一条输入。"""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("placeholder", "输入问题，Enter 发送，Shift+Enter 换行")
        kwargs.setdefault("soft_wrap", True)
        kwargs.setdefault("show_line_numbers", False)
        super().__init__(**kwargs)  # type: ignore[arg-type]

    async def action_submit(self) -> None:
        """发送当前输入内容。"""
        value = self.text.strip()
        if not value:
            return
        self.post_message(self.Submitted(value))
        self.text = ""

    def action_newline(self) -> None:
        """插入一个换行符。"""
        self.insert("\n")
