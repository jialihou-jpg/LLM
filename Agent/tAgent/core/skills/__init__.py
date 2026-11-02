"""Skill 动态加载。

tAgent 初始化时以程序启动时的工作目录为项目根目录，定位 ``.agents/skills``
目录，扫描其中的 Skill 子目录，解析每个 ``SKILL.md`` 文件头的 YAML Frontmatter，
只加载必需的 ``name`` 与 ``description``；完整正文由 :class:`SkillSpec` 惰性读取。
"""

from __future__ import annotations

from core.skills.base import SKILL_MANIFEST, SkillSpec
from core.skills.creator import (
    SKILL_CREATE_TOOL_NAME,
    SkillCreatorTool,
    build_create_skill_tool,
)
from core.skills.loader import (
    DEFAULT_SKILLS_PROJECT_ROOT,
    FRONTMATTER_DELIM,
    SKILLS_DIRNAME,
    discover_skill_dirs,
    discover_skills,
    find_skills_root,
    load_skills,
    parse_frontmatter,
)
from core.skills.prompt import (
    SKILLS_PROMPT_FOOTER,
    SKILLS_PROMPT_HEADER,
    build_skills_prompt,
)
from core.skills.registry import SkillRegistry
from core.skills.tool import (
    LOAD_SKILL_TOOL_NAME,
    SkillLoaderTool,
    build_skill_tools,
)

__all__ = [
    "DEFAULT_SKILLS_PROJECT_ROOT",
    "FRONTMATTER_DELIM",
    "LOAD_SKILL_TOOL_NAME",
    "SKILLS_DIRNAME",
    "SKILLS_PROMPT_FOOTER",
    "SKILLS_PROMPT_HEADER",
    "SKILL_CREATE_TOOL_NAME",
    "SKILL_MANIFEST",
    "SkillCreatorTool",
    "SkillLoaderTool",
    "SkillRegistry",
    "SkillSpec",
    "build_create_skill_tool",
    "build_skill_tools",
    "build_skills_prompt",
    "discover_skill_dirs",
    "discover_skills",
    "find_skills_root",
    "load_skills",
    "parse_frontmatter",
]
