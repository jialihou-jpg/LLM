"""tAgent 核心层。

该包只包含与界面无关的业务逻辑：配置、对话状态、LLM 客户端、工具集与 Agent 编排。
任何前端（TUI / Web / Desktop / Mobile）都只依赖本包，不允许反向依赖。

对外稳定入口见 ``__all__``。
"""

from __future__ import annotations

from core.agent import DEFAULT_SYSTEM_PROMPT, Agent
from core.config import LLMSettings, SearchSettings, Settings
from core.errors import AgentError, ConfigurationError, LLMError, ToolError
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
from core.factory import build_agent, build_default_registry, build_default_skill_registry
from core.llm.client import LLMClient
from core.llm.openai_client import OpenAICompatibleClient
from core.models import Message, ToolCall
from core.session import Session
from core.skills import (
    SkillRegistry,
    SkillSpec,
    build_create_skill_tool,
    build_skill_tools,
    build_skills_prompt,
    load_skills,
)
from core.tools.base import ToolResult, ToolSpec
from core.tools.registry import ToolRegistry

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "Agent",
    "AgentError",
    "AgentEvent",
    "AssistantCompleted",
    "AssistantDelta",
    "ConfigurationError",
    "ErrorRaised",
    "LLMClient",
    "LLMError",
    "LLMSettings",
    "Message",
    "OpenAICompatibleClient",
    "RunCompleted",
    "RunStarted",
    "SearchSettings",
    "Session",
    "Settings",
    "SkillRegistry",
    "SkillSpec",
    "ToolCall",
    "ToolCallCompleted",
    "ToolCallStarted",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_agent",
    "build_create_skill_tool",
    "build_default_registry",
    "build_default_skill_registry",
    "build_skill_tools",
    "build_skills_prompt",
    "load_skills",
]
