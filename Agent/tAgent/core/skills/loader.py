"""Skill 发现与注册（动态加载入口）。

约定：
- 以程序启动时的工作目录（默认 :data:`Path.cwd`）为项目根目录；
- 定位 ``.agents/skills`` 目录，扫描其下的 Skill 子目录；
- 每个 Skill 子目录至少包含一个 ``SKILL.md``，文件头通过 YAML Frontmatter
  声明必需的 ``name`` 与 ``description``；
- 初始化阶段只加载这两个字段，完整正文由 :class:`SkillSpec.body` 惰性读取。

为避免为核心层引入第三方依赖（项目约定核心层零额外依赖），这里内置一个
只覆盖 Skill 元数据所需的极简 YAML Frontmatter 解析器。
"""

from __future__ import annotations

from pathlib import Path

from core.skills.base import FRONTMATTER_DELIM, SKILL_MANIFEST, SkillSpec, split_frontmatter
from core.skills.registry import SkillRegistry

#: Skill 目录（相对项目根），按 Agent Skills 规范位于 ``.agents/skills`` 下
SKILLS_DIRNAME = ".agents/skills"
#: 技能的默认项目根目录（用户指定的当前项目，其 ``.agents/skills`` 下存放技能）
DEFAULT_SKILLS_PROJECT_ROOT = Path(r"D:\office")


# ------------------------------------------------------------------ Frontmatter 解析
def _strip_quotes(value: str) -> str:
    """去掉整段包裹的成对单/双引号。"""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(front: str) -> dict[str, str]:
    """解析 Frontmatter 的顶层键值，返回 ``{key: value}``。

    只处理顶层标量键值：支持 ``key: value``、引号包裹的值，以及用于多行
    ``description`` 的 ``|`` / ``>`` 块标量。数组、嵌套映射等复杂结构会被
    忽略——Skill 元数据只需要 ``name`` 与 ``description``。
    """
    data: dict[str, str] = {}
    lines = front.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        index += 1
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped or stripped.startswith("-"):
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip()
        value = rest.strip()
        if value.startswith("|") or value.startswith(">"):
            # 块标量：收集后续缩进（或空行）的连续行
            block: list[str] = []
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip() or nxt.startswith((" ", "\t")):
                    block.append(nxt)
                    index += 1
                else:
                    break
            # YAML 行为：按块内最小缩进剥离统一前导空白
            indents = [
                len(line) - len(line.lstrip(" \t")) for line in block if line.strip()
            ]
            min_indent = min(indents) if indents else 0
            value = "\n".join(
                (line[min_indent:] if line.strip() else "") for line in block
            ).strip("\n")
        else:
            if not value.startswith(("\"", "'")):
                value = value.split(" #", 1)[0]
            value = _strip_quotes(value)
        data[key] = value
    return data


# ------------------------------------------------------------------ 发现与加载
def find_skills_root(
    project_root: str | Path | None = None,
    dirname: str = SKILLS_DIRNAME,
) -> Path | None:
    """定位 ``.agents/skills`` 目录；不存在时返回 ``None``。

    ``project_root`` 未显式给出时，默认以 :data:`DEFAULT_SKILLS_PROJECT_ROOT`
    （用户指定的当前项目 ``D:\\office``）为项目根。
    """
    root = Path(project_root) if project_root is not None else DEFAULT_SKILLS_PROJECT_ROOT
    candidate = root / dirname
    return candidate if candidate.is_dir() else None


def discover_skill_dirs(
    project_root: str | Path | None = None,
    dirname: str = SKILLS_DIRNAME,
) -> list[Path]:
    """返回 ``.agents/skills`` 下所有含 ``SKILL.md`` 的 Skill 子目录（按名称排序）。"""
    root = find_skills_root(project_root, dirname)
    if root is None:
        return []
    return sorted(
        (
            child
            for child in root.iterdir()
            if child.is_dir() and (child / SKILL_MANIFEST).is_file()
        ),
        key=lambda item: item.name,
    )


def _parse_skill(skill_dir: Path) -> SkillSpec:
    """解析单个 Skill 子目录，只读取 Frontmatter 元数据（不读取正文）。"""
    manifest = skill_dir / SKILL_MANIFEST
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"无法读取 {manifest}：{exc}") from exc

    front, _ = split_frontmatter(text)
    if front is None:
        raise ValueError(f"{manifest} 缺少 YAML Frontmatter（须以 --- 开头）")
    meta = parse_frontmatter(front)

    name = meta.get("name")
    description = meta.get("description")
    if not name:
        raise ValueError(f"{manifest} 缺少必需字段 name")
    if not description:
        raise ValueError(f"{manifest} 缺少必需字段 description")

    return SkillSpec(name=name, description=description, path=skill_dir, frontmatter=meta)


def discover_skills(
    project_root: str | Path | None = None,
    dirname: str = SKILLS_DIRNAME,
) -> tuple[list[SkillSpec], list[str]]:
    """扫描并解析各 Skill 的 Frontmatter，返回 (有效 Skill 列表, 跳过原因列表)。

    某个子目录缺少 ``SKILL.md``、缺少 Frontmatter、或缺少必需字段时，
    不会让整个加载失败，而是记入 ``warnings`` 后跳过。
    """
    skills: list[SkillSpec] = []
    warnings: list[str] = []
    for skill_dir in discover_skill_dirs(project_root, dirname):
        try:
            skills.append(_parse_skill(skill_dir))
        except ValueError as exc:
            warnings.append(str(exc))
    return skills, warnings


def load_skills(
    project_root: str | Path | None = None,
    dirname: str = SKILLS_DIRNAME,
) -> SkillRegistry:
    """发现并注册 Skill（初始化阶段只加载 name 与 description，不读正文）。"""
    skills, _ = discover_skills(project_root, dirname)
    registry = SkillRegistry()
    for skill in skills:
        registry.register(skill)
    return registry


__all__ = [
    "DEFAULT_SKILLS_PROJECT_ROOT",
    "FRONTMATTER_DELIM",
    "SKILLS_DIRNAME",
    "discover_skill_dirs",
    "discover_skills",
    "find_skills_root",
    "load_skills",
    "parse_frontmatter",
]
