"""组装根（Composition Root）。

前端只从这里获取"可用的 Agent 实例"，不需要知道 LLM 客户端、工具注册中心
与会话是如何拼装起来的。更换模型服务商或新增工具时只需改动本文件。
"""

from __future__ import annotations

import os

from core.agent import Agent
from core.config import Settings, load_settings
from core.llm.client import LLMClient
from core.llm.openai_client import OpenAICompatibleClient
from core.session import Session
from core.skills import (
    SkillRegistry,
    build_create_skill_tool,
    build_skill_tools,
    build_skills_prompt,
    load_skills,
)
from core.tools.base import ToolSpec
from core.tools.builtin.cli_tools import build_cli_tools
from core.tools.builtin.datetime_tools import build_datetime_tools
from core.tools.builtin.fetch_web import build_fetch_tools
from core.tools.builtin.filesystem_tools import build_filesystem_tools
from core.tools.builtin.web_search import build_search_tools
from core.tools.registry import ToolRegistry


def build_default_registry(settings: Settings | None = None) -> ToolRegistry:
    """构造内置工具集合（日期时间 + 文件系统 + 网络搜索 + 网页抓取 + 本地 CLI）。"""
    registry = ToolRegistry()
    search_settings = settings.search if settings is not None else None
    tools = (
        build_datetime_tools()
        + build_filesystem_tools()
        + build_search_tools(search_settings)
        + build_fetch_tools()
        + build_cli_tools()
    )
    for tool in tools:
        registry.register(tool)
    return registry


def build_default_skill_registry(
    project_root: str | os.PathLike[str] | None = None,
) -> SkillRegistry:
    """发现并注册项目根目录（默认 ``D:\\office``）下 ``.agents/skills`` 里的 Skill。

    初始化阶段只加载每个 Skill 的 ``name`` 与 ``description``，不读取正文。
    目录不存在时返回空注册中心，不会让应用启动失败。
    """
    return load_skills(project_root=project_root)


def build_client(settings: Settings) -> LLMClient:
    """根据配置构造 LLM 客户端。"""
    return OpenAICompatibleClient(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        timeout=settings.llm.timeout,
    )


def build_agent(
    settings: Settings | None = None,
    *,
    client: LLMClient | None = None,
    registry: ToolRegistry | None = None,
    skills: SkillRegistry | None = None,
    session: Session | None = None,
    extra_tools: list[ToolSpec] | None = None,
    skill_project_root: str | os.PathLike[str] | None = None,
) -> Agent:
    """构造一个开箱即用的 Agent。

    参数全部可选：未显式提供时使用配置文件 + 内置工具 + 新会话。
    ``skills`` 未提供时，默认从 ``skill_project_root``（未给则为
    ``DEFAULT_SKILLS_PROJECT_ROOT``，即 ``D:\\office``）发现并注册 Skill。
    """
    resolved = settings if settings is not None else load_settings()
    tool_registry = registry if registry is not None else build_default_registry(resolved)
    for tool in extra_tools or []:
        tool_registry.register(tool)

    skill_registry = (
        skills if skills is not None else build_default_skill_registry(skill_project_root)
    )
    # 注册 loadSkill 工具：让模型能按提示中的指引，按名加载 Skill 完整指令
    if skill_registry:
        for tool in build_skill_tools(skill_registry):
            tool_registry.register(tool)
    # 注册 createskill 工具：始终可用，让模型能按自然语言要求创建新 Skill
    for tool in build_create_skill_tool(skill_project_root):
        tool_registry.register(tool)

    llm_client = client if client is not None else build_client(resolved)

    # 把发现的 Skill（name + description）注入 System Prompt
    full_prompt = resolved.system_prompt
    skills_block = build_skills_prompt(skill_registry)
    if skills_block:
        full_prompt = f"{full_prompt}\n\n{skills_block}"

    conversation = (
        session
        if session is not None
        else Session(system_prompt=full_prompt, session_id="default")
    )
    return Agent(
        client=llm_client,
        registry=tool_registry,
        skills=skill_registry,
        session=conversation,
        max_rounds=resolved.max_tool_rounds,
        system_prompt=full_prompt,
    )


__all__ = [
    "build_agent",
    "build_client",
    "build_default_registry",
    "build_default_skill_registry",
]
