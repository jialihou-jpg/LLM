"""``createskill`` Function Calling 工具：让 Agent 按用户自然语言创建新 Skill。

调用方（LLM）传入两个参数：

- ``name``：技能名，统一使用小写字母、数字和连字符（kebab-case）；
- ``skillContext``：要写入 ``SKILL.md`` 的完整内容，须以 ``---`` 开头的
  YAML Frontmatter 声明 ``name`` 与 ``description``，后接正文。

工具在项目根的 ``.agents/skills/<name>/`` 下创建 ``SKILL.md`` 并写入内容；
目标技能已存在时返回明确提示、不覆盖。若还需 ``references/``、``scripts/``
等辅助目录或其它辅助文件，由模型继续调用文件系统工具完成。
"""

from __future__ import annotations

import re
from pathlib import Path

from core.skills.base import FRONTMATTER_DELIM, SKILL_MANIFEST, split_frontmatter
from core.skills.loader import (
    DEFAULT_SKILLS_PROJECT_ROOT,
    SKILLS_DIRNAME,
    parse_frontmatter,
)
from core.tools.base import ToolSpec

#: createskill 工具名
SKILL_CREATE_TOOL_NAME = "createskill"
#: 技能名格式：小写字母、数字、连字符（不允许前导/尾随或连续连字符）
_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class SkillCreatorTool:
    """按参数创建新 Skill 目录与 ``SKILL.md``，不覆盖已有技能。"""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self._project_root = (
            Path(project_root)
            if project_root is not None
            else DEFAULT_SKILLS_PROJECT_ROOT
        )

    def __call__(
        self,
        name: str | None = None,
        skillContext: str | None = None,
        **_: object,
    ) -> str:
        return self.create(name, skillContext)

    def create(self, name: str | None, skill_context: str | None) -> str:
        raw_name = (name or "").strip()
        if not _NAME_RE.fullmatch(raw_name):
            return (
                f"非法的技能名 {raw_name!r}：名称只能由小写字母、数字和连字符组成，"
                "例如 my-search-skill。"
            )

        content = (skill_context or "").strip()
        if not content:
            return "缺少 skillContext：请提供要写入 SKILL.md 的完整内容。"

        skill_dir = self._project_root / SKILLS_DIRNAME / raw_name
        manifest = skill_dir / SKILL_MANIFEST
        if manifest.exists():
            return (
                f"技能 {raw_name} 已存在（{manifest}），为避免覆盖原有内容，"
                "未做任何修改。如需修改，请改用文件工具编辑，或换一个名称。"
            )

        normalized, error = _normalize_manifest(content, raw_name)
        if error:
            return error

        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            manifest.write_text(normalized, encoding="utf-8")
        except OSError as exc:
            return f"创建技能 {raw_name} 失败：{exc}"

        front, _ = split_frontmatter(normalized)
        description = parse_frontmatter(front).get("description", "").strip()
        return (
            f"已创建技能 {raw_name}（{manifest}）。"
            f"description：{description or '（未填写）'}。"
            "若还需要 references/、scripts/ 等辅助目录或其它辅助文件，"
            "请继续调用文件系统工具创建。"
        )


# ------------------------------------------------------------------ 内容规整
def _normalize_manifest(content: str, name: str) -> tuple[str, str]:
    """校验并规整待写入的 ``SKILL.md`` 内容。

    返回 ``(规整后的全文, 错误信息)``；错误信息为空表示通过。规整时若
    Frontmatter 的 ``name`` 与目录名不一致，会统一为目录名，保证按名可加载。
    """
    front, body = split_frontmatter(content)
    if front is None:
        return "", (
            "skillContext 必须以 YAML Frontmatter 开头（首行 ---，声明 name 与 "
            "description），再写正文。"
        )
    meta = parse_frontmatter(front)
    if not meta.get("name"):
        return "", "skillContext 的 Frontmatter 缺少必需的 name 字段。"
    if not meta.get("description"):
        return "", "skillContext 的 Frontmatter 缺少必需的 description 字段。"
    if meta["name"].strip() == name:
        return content, ""

    # Frontmatter 的 name 与目录名不一致：统一为目录名，保证可被按名加载
    lines = front.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("name:"):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}name: {name}"
            break
    normalized_front = "\n".join(lines)
    # 重新包上 --- 定界符（split_frontmatter 剥离了它们）
    return (
        f"{FRONTMATTER_DELIM}\n{normalized_front}\n{FRONTMATTER_DELIM}\n\n{body}",
        "",
    )


def build_create_skill_tool(
    project_root: str | Path | None = None,
) -> list[ToolSpec]:
    """构造 ``createskill`` 工具声明（在指定项目根下创建技能，默认启动目录）。"""
    return [
        ToolSpec(
            name=SKILL_CREATE_TOOL_NAME,
            description=(
                "根据用户的自然语言要求创建一个新的 Skill。传 name（技能名，仅由小写"
                "字母、数字和连字符组成）和 skillContext（要写入 SKILL.md 的完整内容，"
                "须以 --- 开头的 YAML Frontmatter 声明 name 与 description，再写正文）。"
                "工具会在当前项目 .agents/skills/<name>/ 下生成 SKILL.md；若技能已存在"
                "则返回提示、不覆盖。还需要 references/、scripts/ 等辅助目录或其它辅助"
                "文件时，请继续调用文件系统工具（创建目录/文件）完成。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "要创建的 Skill 名称（小写字母、数字、连字符）",
                    },
                    "skillContext": {
                        "type": "string",
                        "description": (
                            "要写入 SKILL.md 的完整内容，须包含声明 name 与 "
                            "description 的 YAML Frontmatter 及正文"
                        ),
                    },
                },
                "required": ["name", "skillContext"],
            },
            handler=SkillCreatorTool(project_root),
        )
    ]


__all__ = ["SKILL_CREATE_TOOL_NAME", "SkillCreatorTool", "build_create_skill_tool"]
