"""``loadSkill`` Function Calling 工具：按需加载 Skill 的指令文件。

System Prompt 中只会列出每个 Skill 的 name 与 description，正文保持惰性。
模型通过本工具按名加载：

- 仅传 ``name``：读取该 Skill 的 ``SKILL.md`` 全文并返回；
- 同时传 ``filename``：读取对应的附加文件，不重复加载 ``SKILL.md``。

路径解析规则（``filename``）：
1. 精确路径匹配优先——依次尝试绝对路径、相对 Skill 目录、相对项目根；
2. 只传文件名时，在 Skill 目录内递归搜索，匹配唯一则读取，多个同名则返回候选路径；
3. 读取范围严格限制在指定 Skill 目录内部，越界路径一律拒绝，避免解析错误读到其他文件。
"""

from __future__ import annotations

from pathlib import Path

from core.skills.base import SkillSpec
from core.skills.loader import SKILLS_DIRNAME
from core.skills.registry import SkillRegistry
from core.tools.base import ToolSpec

#: loadSkill 工具名
LOAD_SKILL_TOOL_NAME = "loadSkill"
#: 传给工具、用于列出全部可用技能的特殊取值
_LIST_HINTS = ("", "list", "all", "help")


class SkillLoaderTool:
    """按名加载 Skill 指令文件，并保证读取范围不越出技能目录。"""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def __call__(
        self,
        name: str | None = None,
        filename: str | None = None,
        **_: object,
    ) -> str:
        return self.load(name, filename)

    def load(self, name: str | None, filename: str | None = None) -> str:
        raw_name = (name or "").strip()
        if raw_name.lower() in _LIST_HINTS:
            return self._list_available()
        skill = self._registry.get(raw_name)
        if skill is None:
            return self._list_available(f"未找到技能 {raw_name}，可用技能如下：")

        if filename is None or not str(filename).strip():
            # 仅 name：读取 SKILL.md 全文
            return skill.body
        return self._load_additional(skill, str(filename))

    # ------------------------------------------------------------------ 附加文件
    def _load_additional(self, skill: SkillSpec, filename: str) -> str:
        skill_dir = skill.path.resolve()
        project_root = _project_root_of(skill_dir)
        raw = Path(filename)

        # 1) 精确路径匹配：绝对路径 → 相对技能目录 → 相对项目根
        candidates: list[Path] = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.append(skill_dir / raw)
            candidates.append(project_root / raw)

        for candidate in candidates:
            resolved = _resolve_within(skill_dir, candidate)
            if resolved is None:
                continue  # 越界路径：拒绝读取，跳过
            if resolved.is_file():
                return _read_file(resolved)

        # 2) 裸文件名：在技能目录内递归查找，匹配唯一时读取
        if raw.name == filename:
            matches = sorted(p.resolve() for p in skill_dir.rglob(filename) if p.is_file())
            if len(matches) == 1:
                return _read_file(matches[0])
            if len(matches) > 1:
                listing = "\n".join(f"- {path}" for path in matches)
                return (
                    f"在技能 {skill.name} 目录下找到多个同名文件 {filename}，"
                    f"请指定其一（把 filename 填为完整路径）：\n{listing}"
                )
            return f"在技能 {skill.name} 目录下未找到文件 {filename}"

        return f"未找到文件 {filename}（已在技能 {skill.name} 目录内按精确路径匹配）"

    def _list_available(self, prefix: str = "当前可用技能：") -> str:
        if not self._registry:
            return "当前没有可用技能"
        lines = "\n".join(
            f"- {skill.name}: {skill.description}" for skill in self._registry.all()
        )
        return prefix + "\n" + lines


# ------------------------------------------------------------------ 路径工具
def _project_root_of(skill_dir: Path) -> Path:
    """从技能目录反推项目根。

    技能目录结构为 ``<root>/<SKILLS_DIRNAME>/<name>``，向上剥离
    ``SKILLS_DIRNAME`` 的层级（含技能名本身）即得到项目根。
    """
    root = skill_dir
    for _ in range(len(Path(SKILLS_DIRNAME).parts) + 1):
        root = root.parent
    return root


def _resolve_within(skill_dir: Path, candidate: Path) -> Path | None:
    """把候选路径解析为绝对路径；不在技能目录内或解析失败时返回 ``None``。"""
    try:
        resolved = candidate.resolve()
        resolved.relative_to(skill_dir.resolve())
    except (ValueError, OSError):
        return None
    return resolved


def _read_file(path: Path) -> str:
    """读取文本文件；失败时返回可回传给模型的错误信息。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return f"读取文件 {path} 失败：{exc}"


def build_skill_tools(registry: SkillRegistry) -> list[ToolSpec]:
    """构造 ``loadSkill`` 工具声明（绑定给定的 Skill 注册中心）。"""
    return [
        ToolSpec(
            name=LOAD_SKILL_TOOL_NAME,
            description=(
                "加载某个 Skill 的指令文件。仅传 name 时返回该 Skill 的 SKILL.md "
                "全文；同时传 filename 时加载对应的附加文件（不重复加载 SKILL.md）。"
                "filename 支持相对技能目录、相对项目根或绝对路径，读取范围仅限该 "
                "技能目录内部；只传文件名时在技能目录内递归查找唯一匹配，多个同名"
                "文件时返回候选路径供选择。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "要加载的 Skill 名称（必填）",
                    },
                    "filename": {
                        "type": "string",
                        "description": "可选：要加载的附加文件路径或文件名",
                    },
                },
                "required": ["name"],
            },
            handler=SkillLoaderTool(registry),
        )
    ]


__all__ = ["LOAD_SKILL_TOOL_NAME", "SkillLoaderTool", "build_skill_tools"]
