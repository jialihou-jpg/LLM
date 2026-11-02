"""TUI 层的冒烟测试（使用 Textual 的无头测试模式）。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from textual.pilot import Pilot

from core.agent import Agent
from core.tools.registry import ToolRegistry
from tests.fakes import FakeLLMClient, text_events, tool_events
from tui.app import TAgentApp
from tui.widgets.chat_log import ChatLog, ToolCallPanel
from tui.widgets.prompt_input import PromptInput
from tui.widgets.status_bar import StatusBar


def build_app(client: FakeLLMClient) -> TAgentApp:
    registry = ToolRegistry()
    registry.register_function(
        "echo",
        "回显",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        lambda **kwargs: f"echo:{kwargs.get('text')}",
    )
    agent = Agent(client=client, registry=registry, max_rounds=3, system_prompt="测试")
    return TAgentApp(agent=agent)


def run(
    client: FakeLLMClient,
    scenario: Callable[[TAgentApp, Pilot], Awaitable[None]],
) -> None:
    """在独立事件循环中执行一段 TUI 场景。"""

    async def main() -> None:
        app = build_app(client)
        async with app.run_test() as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(main())


def test_app_mounts_and_shows_welcome() -> None:
    async def scenario(app: TAgentApp, pilot: Pilot) -> None:
        chat = app.query_one(ChatLog)
        assert chat.query(".info-message")

    run(FakeLLMClient([]), scenario)


def test_submitting_message_renders_answer() -> None:
    async def scenario(app: TAgentApp, pilot: Pilot) -> None:
        app.query_one(PromptInput).text = "你好"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        chat = app.query_one(ChatLog)
        assert chat.query(".user-message")
        assert chat.query(".assistant-message")
        # 渲染过程不应产生错误提示
        assert not chat.query(".error-message")
        status = app.query_one(StatusBar)
        assert "就绪" in status.plain_text

    run(FakeLLMClient([text_events("回答", "内容")]), scenario)


def test_tool_call_is_rendered_with_result() -> None:
    async def scenario(app: TAgentApp, pilot: Pilot) -> None:
        app.query_one(PromptInput).text = "调用工具"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        chat = app.query_one(ChatLog)
        panels = list(chat.query(".tool-message"))
        assert panels, "应当渲染工具调用面板"
        panel = panels[0]
        assert isinstance(panel, ToolCallPanel)
        assert "echo" in panel.plain_text
        assert "echo:hi" in panel.plain_text
        assert not chat.query(".error-message")

    run(FakeLLMClient([tool_events("echo", '{"text": "hi"}'), text_events("好的")]), scenario)


def test_slash_command_is_handled_locally() -> None:
    async def scenario(app: TAgentApp, pilot: Pilot) -> None:
        app.query_one(PromptInput).text = "/help"
        await pilot.press("enter")
        await pilot.pause()

        chat = app.query_one(ChatLog)
        assert chat.query(".info-message")

    run(FakeLLMClient([]), scenario)


def test_enter_key_submits_input() -> None:
    async def scenario(app: TAgentApp, pilot: Pilot) -> None:
        prompt = app.query_one(PromptInput)
        prompt.text = "换行测试"
        await pilot.press("enter")
        await pilot.pause()
        # 提交后输入框被清空
        assert prompt.text == ""

    run(FakeLLMClient([]), scenario)


def test_model_error_is_shown_as_error_message() -> None:
    class BoomClient(FakeLLMClient):
        async def stream(self, messages, tools=None):  # type: ignore[override]
            raise RuntimeError("网络炸了")
            yield  # pragma: no cover

    async def scenario(app: TAgentApp, pilot: Pilot) -> None:
        app.query_one(PromptInput).text = "你好"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        chat = app.query_one(ChatLog)
        assert chat.query(".error-message")

    run(BoomClient([]), scenario)
