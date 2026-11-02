"""底部状态栏。"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

STATE_STYLES: dict[str, str] = {
    "idle": "green",
    "busy": "yellow",
    "error": "red",
}


class StatusBar(Static):
    """展示模型、工作目录与当前状态。"""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._state = "idle"
        self._status = "就绪"
        self._model = "-"
        self._cwd = "-"
        self._line = Text()

    @property
    def plain_text(self) -> str:
        """当前状态栏的纯文本内容（便于测试与调试）。"""
        return self._line.plain

    def set_status(self, text: str, state: str = "idle") -> None:
        """设置状态文本与状态类型。"""
        self._status = text
        self._state = state
        self.refresh_status()

    def set_model(self, model: str) -> None:
        self._model = model or "-"
        self.refresh_status()

    def set_cwd(self, path: str) -> None:
        self._cwd = path or "-"
        self.refresh_status()

    def refresh_status(self) -> None:
        """重新渲染状态栏文本。"""
        color = STATE_STYLES.get(self._state, "green")
        text = Text()
        text.append("● ", style=f"bold {color}")
        text.append(self._status, style=color)
        text.append("  │  ", style="dim")
        text.append("模型 ", style="dim")
        text.append(self._model)
        text.append("  │  ", style="dim")
        text.append("目录 ", style="dim")
        text.append(self._cwd)
        self._line = text
        self.update(text)
