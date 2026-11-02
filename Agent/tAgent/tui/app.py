"""tAgent 的 Textual 应用。

职责：
- 组装界面（对话区、输入框、状态栏）
- 把 :mod:`core` 的事件流渲染成界面元素
- 处理界面层的交互（斜杠命令、清空、退出）

界面层不包含任何业务规则：所有模型调用与工具执行都委托给 :class:`core.agent.Agent`。
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from core.agent import Agent
from core.config import Settings, load_settings
from core.errors import ConfigurationError
from core.events import (
    AssistantCompleted,
    AssistantDelta,
    ErrorRaised,
    RunCompleted,
    ToolCallCompleted,
    ToolCallStarted,
)
from core.factory import build_agent
from core.tools.base import ToolSpec
from tui import commands
from tui.widgets.chat_log import AssistantMessage, ChatLog, ToolCallPanel
from tui.widgets.prompt_input import PromptInput
from tui.widgets.status_bar import StatusBar

FLUSH_INTERVAL = 0.06
WELCOME_TEXT = (
    "欢迎使用 tAgent。输入问题后按 Enter 发送，Shift+Enter 换行；"
    "输入 /help 查看可用命令。"
)


class TAgentApp(App[None]):
    """tAgent 终端界面。"""

    CSS_PATH = "theme.tcss"
    TITLE = "tAgent"
    SUB_TITLE = "Core + Textual"

    BINDINGS = [
        Binding("ctrl+q", "quit", "退出", priority=True),
        Binding("ctrl+l", "clear_chat", "清空", priority=True),
        Binding("f1", "show_help", "帮助", priority=True),
    ]

    def __init__(
        self,
        agent: Agent | None = None,
        settings: Settings | None = None,
        *,
        agent_factory: Callable[[Settings], Agent] | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._settings = settings
        self._agent_factory = agent_factory or build_agent
        self._busy = False
        self._last_flush = 0.0

    # ------------------------------------------------------------------ 状态
    @property
    def agent(self) -> Agent | None:
        return self._agent

    @property
    def settings(self) -> Settings | None:
        return self._settings

    @property
    def busy(self) -> bool:
        return self._busy

    # ------------------------------------------------------------------ 布局
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ChatLog(id="chat")
        yield StatusBar(id="status")
        yield PromptInput(id="prompt")
        yield Footer()

    async def on_mount(self) -> None:
        chat = self.query_one(ChatLog)
        chat.add_info(WELCOME_TEXT)

        # 启动时发现外部 MCP Server 工具（异步连接，单个 Server 故障被隔离）
        mcp_specs = await self._discover_mcp_tools(chat)

        try:
            if self._agent is None:
                if self._settings is None:
                    self._settings = load_settings()
                # 默认工厂支持注入外部 MCP 工具；自定义工厂保持原签名兼容
                if self._agent_factory is build_agent:
                    self._agent = build_agent(self._settings, extra_tools=mcp_specs)
                else:
                    self._agent = self._agent_factory(self._settings)
        except ConfigurationError as exc:
            chat.add_error(str(exc))
            self.query_one(PromptInput).disabled = True
            self.query_one(StatusBar).set_status("配置错误", "error")
            return

        status = self.query_one(StatusBar)
        status.set_model(self._model_label())
        status.set_cwd(_safe_cwd())
        self.query_one(PromptInput).focus()

    async def _discover_mcp_tools(self, chat: ChatLog) -> list[ToolSpec]:
        """读取 ``.mcp.json`` 并异步发现外部 MCP 工具；任何 MCP 错误都不阻断启动。"""
        try:
            from core.mcp import discover_mcp_tool_specs, load_mcp_servers
        except Exception as exc:  # mcp SDK 未安装等
            chat.add_info(f"[MCP] 跳过外部 MCP 加载：{exc}")
            return []

        servers, cfg_warnings = load_mcp_servers()
        for warning in cfg_warnings:
            chat.add_info(f"[MCP] {warning}")
        if not servers:
            return []

        try:
            specs, conn_warnings = await discover_mcp_tool_specs(servers)
        except Exception as exc:  # 兜底：任何意外都不让启动失败
            chat.add_error(f"[MCP] 加载外部工具失败：{exc}")
            return []
        for warning in conn_warnings:
            chat.add_info(f"[MCP] {warning}")
        return specs

    # ------------------------------------------------------------------ 交互
    def _model_label(self) -> str:
        """状态栏展示的模型名。"""
        if self._settings is not None:
            return self._settings.llm.model
        model = getattr(self._agent.client, "model", None) if self._agent else None
        return str(model) if model else "-"

    def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        """处理用户提交。"""
        value = event.value.strip()
        if not value:
            return
        if value.startswith("/"):
            commands.dispatch(self, value)
            return
        if self._busy:
            self.query_one(ChatLog).add_info("上一条请求仍在处理中，请稍候……")
            return
        if self._agent is None:
            self.query_one(ChatLog).add_error("Agent 尚未初始化，无法处理请求")
            return

        self._busy = True
        self.query_one(PromptInput).disabled = True
        self.query_one(StatusBar).set_status("思考中…", "busy")
        self.run_worker(self._consume(value), exclusive=True)

    async def _consume(self, question: str) -> None:
        """消费核心层事件流并渲染界面。"""
        chat = self.query_one(ChatLog)
        chat.add_user(question)

        bubble: AssistantMessage | None = None
        buffer = ""
        panels: dict[str, ToolCallPanel] = {}
        success = True

        try:
            assert self._agent is not None
            async for event in self._agent.run(question):
                if isinstance(event, AssistantDelta):
                    buffer += event.text
                    if bubble is None:
                        bubble = chat.add_assistant()
                    self._flush(bubble, buffer)
                elif isinstance(event, ToolCallStarted):
                    panels[event.call_id] = chat.add_tool_call(event.name, event.arguments)
                elif isinstance(event, ToolCallCompleted):
                    panel = panels.pop(event.call_id, None)
                    if panel is not None:
                        chat.update_tool_call(panel, event.result, event.ok)
                elif isinstance(event, ErrorRaised):
                    success = False
                    chat.add_error(event.message)
                elif isinstance(event, AssistantCompleted):
                    if bubble is not None:
                        # 以本轮的最终文本为准，覆盖流式过程中可能残留的模板碎片
                        self._flush(bubble, event.text, force=True)
                        bubble = None
                        buffer = ""
                elif isinstance(event, RunCompleted):
                    success = event.success
        except Exception as exc:  # pragma: no cover - 兜底保护
            success = False
            chat.add_error(f"处理失败：{exc}")
        finally:
            if bubble is not None and buffer:
                self._flush(bubble, buffer, force=True)
            self._busy = False
            status = self.query_one(StatusBar)
            status.set_status("就绪" if success else "已出错", "idle" if success else "error")
            prompt = self.query_one(PromptInput)
            prompt.disabled = False
            prompt.focus()

    def _flush(self, widget: AssistantMessage, text: str, *, force: bool = False) -> None:
        """节流刷新流式内容，避免频繁重排。"""
        now = time.monotonic()
        if force or now - self._last_flush >= FLUSH_INTERVAL:
            self._last_flush = now
            widget.set_markdown(text)

    # ------------------------------------------------------------------ 动作
    def action_clear_chat(self) -> None:
        """清空对话记录（Ctrl+L）。"""
        self.clear_conversation()

    def action_show_help(self) -> None:
        """展示帮助信息（F1）。"""
        commands.dispatch(self, "/help")

    def clear_conversation(self) -> None:
        """清空界面与核心层会话。"""
        self.query_one(ChatLog).clear()
        if self._agent is not None:
            self._agent.reset()
        self.query_one(ChatLog).add_info("对话已清空。")

    async def on_unmount(self) -> None:
        """退出时释放模型客户端资源。"""
        if self._agent is not None:
            await self._agent.aclose()


def _safe_cwd() -> str:
    try:
        return os.getcwd()
    except OSError:  # pragma: no cover - 极端情况
        return "-"


def main() -> None:  # pragma: no cover - 便捷入口
    TAgentApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
