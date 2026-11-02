"""Skill 注册中心。

保存初始化阶段解析出的 Skill 元数据，按 ``name`` 索引。正文保持惰性，
只在需要执行时通过 :class:`SkillSpec` 读取。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from core.skills.base import SkillSpec


class SkillRegistry:
    """Skill 集合（初始化阶段只含 name / description 元数据）。"""

    def __init__(self, skills: Iterable[SkillSpec] = ()) -> None:
        self._skills: dict[str, SkillSpec] = {}
        for skill in skills:
            self.register(skill)

    # ------------------------------------------------------------------ 注册
    def register(self, skill: SkillSpec) -> SkillSpec:
        """注册（或按 name 覆盖）一个 Skill。"""
        if not skill.name:
            raise ValueError("Skill 名称不能为空")
        self._skills[skill.name] = skill
        return skill

    # ------------------------------------------------------------------ 查询
    def get(self, name: str) -> SkillSpec | None:
        return self._skills.get(name)

    def names(self) -> list[str]:
        return list(self._skills)

    def all(self) -> list[SkillSpec]:
        return list(self._skills.values())

    def summaries(self) -> list[dict[str, str]]:
        """初始化阶段对外暴露的轻量元数据（仅 name + description）。"""
        return [
            {"name": skill.name, "description": skill.description}
            for skill in self._skills.values()
        ]

    def __contains__(self, name: object) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self) -> Iterator[SkillSpec]:
        return iter(self._skills.values())


__all__ = ["SkillRegistry"]
