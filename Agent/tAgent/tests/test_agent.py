"""Agent 编排逻辑的测试。"""

from __future__ import annotations

from core.agent import Agent
from core.events import (
    AssistantCompleted,
    AssistantDelta,
    ErrorRaised,
    RunCompleted,
    RunStarted,
    ToolCallCompleted,
    ToolCallStarted,
)
from core.tools.registry import ToolRegistry
from tests.fakes import FakeLLMClient, text_events, tool_events


def make_agent(client: FakeLLMClient, registry: ToolRegistry | None = None) -> Agent:
    return Agent(
        client=client,
        registry=registry if registry is not None else ToolRegistry(),
        max_rounds=3,
        system_prompt="测试",
    )


def test_simple_answer_stream() -> None:
    client = FakeLLMClient([text_events("你好", "，世界")])
    agent = make_agent(client)

    events = []
    async def collect() -> None:
        async for event in agent.run("hi"):
            events.append(event)

    import asyncio

    asyncio.run(collect())

    assert isinstance(events[0], RunStarted)
    assert any(isinstance(e, AssistantDelta) and e.text == "你好" for e in events)
    assert any(isinstance(e, AssistantCompleted) and e.text == "你好，世界" for e in events)
    assert isinstance(events[-1], RunCompleted) and events[-1].success is True


def test_tool_call_roundtrip() -> None:
    registry = ToolRegistry()
    registry.register_function(
        "echo",
        "回显文本",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        lambda **kwargs: f"echo:{kwargs.get('text')}",
    )
    client = FakeLLMClient(
        [
            tool_events("echo", '{"text": "hi"}'),
            text_events("完成"),
        ]
    )
    agent = make_agent(client, registry)

    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    started = [e for e in events if isinstance(e, ToolCallStarted)]
    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert started and started[0].name == "echo"
    assert started[0].arguments == {"text": "hi"}
    assert completed and completed[0].ok is True
    assert "echo:hi" in completed[0].result
    # 工具结果已经写回会话
    tool_messages = [m for m in agent.history if m.role == "tool"]
    assert tool_messages and "echo:hi" in tool_messages[0].content


def test_async_tool_call_roundtrip() -> None:
    registry = ToolRegistry()

    async def echo_async(**kwargs: object) -> str:
        return f"async:{kwargs.get('text')}"

    registry.register_function(
        "echo_async",
        "异步回显文本",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        echo_async,
    )
    client = FakeLLMClient(
        [
            tool_events("echo_async", '{"text": "hi"}'),
            text_events("完成"),
        ]
    )
    agent = make_agent(client, registry)

    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert completed and completed[0].ok is True
    assert "async:hi" in completed[0].result


def test_broken_arguments_are_reported_to_model() -> None:
    registry = ToolRegistry()
    registry.register_function(
        "noop", "无操作", {"type": "object", "properties": {}}, lambda **_: "ok"
    )
    client = FakeLLMClient([tool_events("noop", "{不是合法 JSON")])
    agent = make_agent(client, registry)

    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert completed and completed[0].ok is False
    assert "解析失败" in completed[0].result


def test_wrapped_tool_arguments_are_unwrapped() -> None:
    """服务商把整段工具调用包一层时，仍能正确取到参数。"""
    registry = ToolRegistry()
    registry.register_function(
        "echo",
        "回显文本",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        lambda **kwargs: f"echo:{kwargs.get('text')}",
    )
    client = FakeLLMClient(
        [
            tool_events("echo", '{{"name": "echo", "arguments": {"text": "hi"}}}'),
            text_events("完成"),
        ]
    )
    agent = make_agent(client, registry)

    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    started = [e for e in events if isinstance(e, ToolCallStarted)]
    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert started and started[0].arguments == {"text": "hi"}
    assert started and started[0].name == "echo"
    assert completed and completed[0].ok is True
    assert "echo:hi" in completed[0].result
    # 回传给服务商的 assistant 消息里，工具名与参数都必须是干净的
    assistant = [m for m in agent.history if m.role == "assistant" and m.tool_calls]
    assert assistant
    call = assistant[0].tool_calls[0]
    assert call.name == "echo"
    assert call.arguments == '{"text": "hi"}'


def test_tool_call_is_normalized_before_roundtrip() -> None:
    """服务商混入碎片、缺少 id 时，回传的消息依然干净可用。"""
    registry = ToolRegistry()
    registry.register_function(
        "echo",
        "回显文本",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        lambda **kwargs: f"echo:{kwargs.get('text')}",
    )
    client = FakeLLMClient(
        [
            tool_events("echo", ' {"text": "hi"}}}\n</tool_call>', call_id=""),
            text_events("完成"),
        ]
    )
    agent = make_agent(client, registry)

    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    completed = [e for e in events if isinstance(e, ToolCallCompleted)]
    assert completed and completed[0].ok is True
    assert "echo:hi" in completed[0].result

    assistant = [m for m in agent.history if m.role == "assistant" and m.tool_calls]
    assert assistant
    call = assistant[0].tool_calls[0]
    assert call.arguments == '{"text": "hi"}'
    assert call.id


def test_client_error_is_reported() -> None:
    class BoomClient(FakeLLMClient):
        async def stream(self, messages, tools=None):  # type: ignore[override]
            raise RuntimeError("网络炸了")
            yield  # pragma: no cover

    agent = make_agent(BoomClient([]))
    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    errors = [e for e in events if isinstance(e, ErrorRaised)]
    completed = [e for e in events if isinstance(e, RunCompleted)]
    assert errors and "网络炸了" in errors[0].message
    assert completed and completed[0].success is False


def test_ask_returns_final_text() -> None:
    client = FakeLLMClient([text_events("最终答案")])
    agent = make_agent(client)

    import asyncio

    assert asyncio.run(agent.ask("hi")) == "最终答案"


def test_each_round_emits_assistant_completed() -> None:
    registry = ToolRegistry()
    registry.register_function(
        "noop", "无操作", {"type": "object", "properties": {}}, lambda **_: "ok"
    )
    client = FakeLLMClient([tool_events("noop", "{}"), text_events("好了")])
    agent = make_agent(client, registry)

    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    completed = [e for e in events if isinstance(e, AssistantCompleted)]
    assert len(completed) == 2  # 每个模型轮次各一个


def test_tool_call_tail_is_stripped() -> None:
    from core.llm.types import ContentDelta, ToolCallDelta

    class MixedClient(FakeLLMClient):
        async def stream(self, messages, tools=None):  # type: ignore[override]
            yield ContentDelta(text="正文 }")
            yield ToolCallDelta(index=0, id="c1", name="noop", arguments="{}")

    registry = ToolRegistry()
    registry.register_function(
        "noop", "无操作", {"type": "object", "properties": {}}, lambda **_: "ok"
    )
    agent = make_agent(MixedClient([]), registry)

    import asyncio

    events = []

    async def collect() -> None:
        async for event in agent.run("go"):
            events.append(event)

    asyncio.run(collect())

    completed = [e for e in events if isinstance(e, AssistantCompleted)]
    assert completed and completed[0].text == "正文"
