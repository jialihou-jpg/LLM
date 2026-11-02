"""Agent 核心编排。

职责边界：
- ``core`` 层负责"做什么"：调用模型 → 解析工具调用 → 执行工具 → 回传结果 → 循环。
- 各前端负责"怎么展示"：消费这里产出的事件流。

Agent 不感知任何界面组件，也不直接打印任何内容。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable, Sequence
from typing import Any
from uuid import uuid4

from core.errors import AgentError
from core.events import (
    AgentEvent,
    AssistantCompleted,
    AssistantDelta,
    ErrorRaised,
    RunCompleted,
    RunStarted,
    ToolCallCompleted,
    ToolCallStarted,
)
from core.llm.client import LLMClient
from core.llm.types import ContentDelta, ToolCallDelta, Usage
from core.models import Message, ToolCall
from core.prompts import DEFAULT_SYSTEM_PROMPT
from core.session import Session
from core.skills.registry import SkillRegistry
from core.tools.registry import ToolRegistry
from core.utils.text import (
    parse_json_object,
    strip_template_fragments,
    strip_tool_call_tail,
    unwrap_tool_arguments,
)


class Agent:
    """带工具调用能力的对话代理。"""

    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry | None = None,
        skills: SkillRegistry | None = None,
        session: Session | None = None,
        *,
        max_rounds: int = 10,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._client = client
        self._registry = registry if registry is not None else ToolRegistry()
        self._skills = skills if skills is not None else SkillRegistry()
        self._session = session if session is not None else Session(system_prompt)
        self._max_rounds = max(1, max_rounds)
        self._running = False
        self._usage = Usage()

    # ------------------------------------------------------------------ 状态
    @property
    def client(self) -> LLMClient:
        return self._client

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def skills(self) -> SkillRegistry:
        return self._skills

    @property
    def session(self) -> Session:
        return self._session

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    @property
    def usage(self) -> Usage:
        return self._usage

    @property
    def history(self) -> list[Message]:
        """当前会话的消息历史。"""
        return self._session.messages

    def reset(self) -> None:
        """清空对话历史，保留系统提示词。"""
        self._session.reset()

    # ------------------------------------------------------------------ 主流程
    async def run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """处理一次用户输入，按顺序产出事件。"""
        if self._running:
            raise AgentError("Agent 正在处理中，请等待当前请求结束")
        self._running = True
        try:
            async for event in self._run(user_input):
                yield event
        finally:
            self._running = False

    async def _run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        yield RunStarted(user_input=user_input)
        self._session.add_user(user_input)

        for round_index in range(1, self._max_rounds + 1):
            raw_parts: list[str] = []
            tool_calls: dict[int, ToolCall] = {}

            try:
                async for event in self._client.stream(
                    self._session.messages, self._registry.schemas()
                ):
                    if isinstance(event, ContentDelta):
                        raw_parts.append(event.text)
                        cleaned = strip_template_fragments(event.text)
                        if cleaned:
                            yield AssistantDelta(text=cleaned)
                    elif isinstance(event, ToolCallDelta):
                        slot = tool_calls.setdefault(event.index, ToolCall())
                        if event.id:
                            slot.id = event.id
                        if event.name:
                            slot.name = event.name
                        slot.arguments += event.arguments
                    elif isinstance(event, Usage):
                        self._usage = event
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield ErrorRaised(message=f"请求出错：{exc}", detail=repr(exc))
                yield RunCompleted(rounds=round_index, success=False)
                return

            answer = strip_template_fragments("".join(raw_parts))
            calls = [tool_calls[key] for key in sorted(tool_calls)]
            for call in calls:
                self._normalize_tool_call(call)
            if calls:
                # 以工具调用结束的轮次，正文尾部可能是服务商泄漏的 JSON 残片
                answer = strip_tool_call_tail(answer)

            yield AssistantCompleted(text=answer)

            if not calls:
                self._session.add_assistant(answer)
                yield RunCompleted(rounds=round_index, success=True)
                return

            self._session.add_assistant(answer, calls)

            for call in calls:
                async for event in self._execute_tool(call):
                    yield event

        yield ErrorRaised(message=f"已达到最大工具调用轮次（{self._max_rounds}），本轮提前结束")
        yield RunCompleted(rounds=self._max_rounds, success=False)

    @staticmethod
    def _normalize_tool_call(call: ToolCall) -> None:
        """修正服务商返回的工具调用中的常见畸形。

        1. 整段工具调用被塞进 ``arguments``（``{"name": "x", "arguments": {...}}``）：
           工具名与真实参数都藏在参数串里，不还原的话回传给服务商的 assistant
           消息会缺少工具名（部分服务商会直接报 400）。
        2. 参数里混入了服务商泄漏的碎片（如 ``}}</tool_call>``）：重新序列化后再回传。
        3. 缺少调用 id：补一个，避免服务商校验失败。
        """
        parsed, error = parse_json_object(call.arguments)
        if error is None and parsed:
            if set(parsed) == {"name", "arguments"}:
                inner = parsed.get("arguments")
                wrapped_name = parsed.get("name")
                if isinstance(inner, dict) and isinstance(wrapped_name, str):
                    if not call.name:
                        call.name = wrapped_name
                    parsed = inner
            call.arguments = json.dumps(parsed, ensure_ascii=False)
        if not call.id:
            call.id = f"call_{uuid4().hex[:12]}"

    async def _execute_tool(self, call: ToolCall) -> AsyncIterator[AgentEvent]:
        """执行单个工具调用，并把结果写回会话。"""
        arguments, error = parse_json_object(call.arguments)
        if error is not None:
            yield ToolCallStarted(call_id=call.id, name=call.name, arguments={})
            result_text = f"{error}，请重新调用该工具并传入正确参数"
            ok = False
        else:
            payload = unwrap_tool_arguments(arguments or {})
            yield ToolCallStarted(call_id=call.id, name=call.name, arguments=payload)
            result = await self._registry.acall(call.name, payload)
            ok = result.ok
            # result.error 已由注册中心统一包装为清晰的中文错误，不再重复加前缀
            result_text = result.output if result.ok else result.error

        self._session.add_tool_result(call.id, result_text, name=call.name)
        yield ToolCallCompleted(
            call_id=call.id, name=call.name, result=result_text, ok=ok
        )

    # ------------------------------------------------------------------ 便捷方法
    async def ask(self, user_input: str) -> str:
        """处理一次输入并返回最终回答文本（不关心事件时使用）。"""
        answer = ""
        async for event in self.run(user_input):
            if isinstance(event, AssistantCompleted):
                answer = event.text
        return answer

    async def aclose(self) -> None:
        """释放底层资源。"""
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()

    def register_tools(self, tools: Iterable[Any]) -> None:
        """批量注册工具。"""
        for tool in tools:
            self._registry.register(tool)

    def schemas(self) -> Sequence[dict[str, Any]]:
        """当前可用的工具声明。"""
        return self._registry.schemas()


__all__ = ["Agent"]
