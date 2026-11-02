"""Skill 注入 System Prompt。

把初始化阶段发现的 Skill（仅 name 与 description）整理成一段可追加到系统提示词
的说明，让模型知道当前有哪些可用技能，以及如何按需通过 ``loadSkill`` 工具加载
完整指令。
"""

from __future__ import annotations

from core.skills.registry import SkillRegistry

#: 可用技能清单的引导语
SKILLS_PROMPT_HEADER = "You have access to the following skills:"
#: 如何按需加载技能的说明
SKILLS_PROMPT_FOOTER = (
    "Use the 'loadSkill' tool to load the full instructions of a skill when needed. "
    "You can also load additional files referenced by a skill."
)


def build_skills_prompt(registry: SkillRegistry) -> str:
    """把发现的 Skill（name + description）整理成注入 System Prompt 的段落。

    没有可用 Skill 时返回空字符串，调用方不应追加空段落。
    """
    if not registry:
        return ""
    listing = "\n".join(
        f"'{skill.name}': {skill.description}" for skill in registry.all()
    )
    return f"{SKILLS_PROMPT_HEADER}\n\n{listing}\n\n{SKILLS_PROMPT_FOOTER}"


__all__ = [
    "SKILLS_PROMPT_FOOTER",
    "SKILLS_PROMPT_HEADER",
    "build_skills_prompt",
]
