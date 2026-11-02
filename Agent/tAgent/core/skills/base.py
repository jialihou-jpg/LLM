"""Skill 抽象。

一个 Skill 对应 ``.agentskills`` 目录下某个子目录里的 ``SKILL.md``。初始化阶段
只从文件头的 YAML Frontmatter 解析出必需的 ``name`` 与 ``description`` 两个字段，
完整的正文不参与加载，由 :meth:`SkillSpec.body` 在真正需要时惰性读取。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: Skill 清单文件名，约定每个 Skill 子目录至少包含一个该文件
SKILL_MANIFEST = "SKILL.md"
#: Frontmatter 分隔符
FRONTMATTER_DELIM = "---"
#: 文件开头的定界行（不含换行）
_FRONTMATTER_OPEN = FRONTMATTER_DELIM + "\n"


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """把 ``SKILL.md`` 内容拆成 (frontmatter 原文, 正文)。

    文件不以 ``---`` 开头、或找不到收尾定界行时，认为没有 Frontmatter，
    返回 ``(None, 原文)``。
    """
    text = text.lstrip("\ufeff")
    if not text.startswith(_FRONTMATTER_OPEN):
        return None, text
    lines = text.splitlines()
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIM:
            end = index
            break
    if end is None:
        return None, text
    front = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return front, body


@dataclass(slots=True)
class SkillSpec:
    """Skill 声明（初始化阶段仅含 Frontmatter 元数据，不含正文）。"""

    name: str
    description: str
    path: Path
    frontmatter: dict[str, str] = field(default_factory=dict)
    _body: str | None = field(default=None, repr=False)

    @property
    def body(self) -> str:
        """惰性读取 ``SKILL.md`` 正文（剥离文件头的 Frontmatter）；首次访问才读盘。"""
        if self._body is None:
            text = (self.path / SKILL_MANIFEST).read_text(encoding="utf-8")
            front, body = split_frontmatter(text)
            self._body = body if front is not None else text
        return self._body

    def reload_body(self) -> None:
        """丢弃已缓存正文，下次访问 :attr:`body` 时重新读盘。"""
        self._body = None


__all__ = ["FRONTMATTER_DELIM", "SKILL_MANIFEST", "SkillSpec", "split_frontmatter"]
