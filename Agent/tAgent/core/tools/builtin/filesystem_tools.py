"""本地文件系统工具（只依赖 Python 标准库）。"""

from __future__ import annotations

import mimetypes
import os
import shutil

from core.tools.base import ToolSpec
from core.utils.files import is_text_file, read_text_file, resolve_path

STR_PATH = {"type": "string", "description": "路径，可为绝对路径或相对当前工作目录的路径"}


def get_cwd(**_: object) -> str:
    """获取当前工作目录。"""
    return os.getcwd()


def list_dir(path: str | None = None, **_: object) -> str:
    """列出指定目录下所有文件和子目录（省略路径时列出当前工作目录）。"""
    target = resolve_path(path or ".")
    if not os.path.isdir(target):
        raise NotADirectoryError(f"目录不存在：{target}")
    lines: list[str] = []
    for name in sorted(os.listdir(target), key=str.lower):
        full = os.path.join(target, name)
        if os.path.isdir(full):
            lines.append(f"[目录] {name}")
        else:
            lines.append(f"[文件] {name} ({os.path.getsize(full)} 字节)")
    body = "\n".join(lines) if lines else "(空目录)"
    return f"{target} 下共 {len(lines)} 项：\n{body}"


def get_file_type(path: str | None = None, **_: object) -> str:
    """获取指定文件的文件类型（扩展名、MIME 类型、文本或二进制）。"""
    target = resolve_path(path)
    if not os.path.exists(target):
        raise FileNotFoundError(f"路径不存在：{target}")
    if os.path.isdir(target):
        return f"{target} 是目录"
    mime, encoding = mimetypes.guess_type(target)
    ext = os.path.splitext(target)[1] or "(无扩展名)"
    kind = "纯文本文件" if is_text_file(target) else "二进制文件"
    parts = [f"{target} 是{kind}", f"扩展名：{ext}", f"MIME类型：{mime or '未知'}"]
    if encoding:
        parts.append(f"压缩/编码：{encoding}")
    parts.append(f"大小：{os.path.getsize(target)} 字节")
    return "；".join(parts)


def read_file(path: str | None = None, encoding: str | None = None, **_: object) -> str:
    """获取指定文件的内容，仅支持纯文本格式文件。"""
    target = resolve_path(path)
    text = read_text_file(target, encoding)
    return f"{target}（{len(text)} 字符）：\n{text}"


def create_file(
    dir: str | None = None,
    filename: str | None = None,
    content: str = "",
    **_: object,
) -> str:
    """根据指定的目录和文件名创建新文件。"""
    if not filename:
        raise ValueError("缺少参数 filename")
    folder = resolve_path(dir) if dir else os.getcwd()
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, str(filename))
    if os.path.exists(target):
        raise FileExistsError(f"文件已存在：{target}")
    with open(target, "w", encoding="utf-8", newline="") as handle:
        handle.write(content or "")
    return f"已创建文件：{target}（{len(content or '')} 字符）"


def edit_file(
    path: str | None = None,
    content: str = "",
    old_text: str | None = None,
    **_: object,
) -> str:
    """编辑指定文件的内容，仅支持纯文本格式文件。

    不传 ``old_text`` 时整体覆盖，传 ``old_text`` 时把其中的内容替换为 ``content``。
    """
    target = resolve_path(path)
    if not os.path.isfile(target):
        raise FileNotFoundError(f"文件不存在：{target}")
    if not is_text_file(target):
        raise ValueError("仅支持纯文本格式文件，该文件疑似二进制文件")
    if old_text is None:
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(content or "")
        return f"已覆盖写入 {target}（{len(content or '')} 字符）"
    text = read_text_file(target)
    if old_text not in text:
        raise ValueError("在文件中未找到 old_text，未做任何修改")
    text = text.replace(old_text, content or "", 1)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return f"已编辑 {target}（替换 1 处，现 {len(text)} 字符）"


def create_dir(path: str | None = None, **_: object) -> str:
    """创建新目录（包含多级目录）。"""
    target = resolve_path(path)
    if os.path.isdir(target):
        return f"目录已存在：{target}"
    os.makedirs(target, exist_ok=False)
    return f"已创建目录：{target}"


def delete_dir(path: str | None = None, **_: object) -> str:
    """删除目录及其下所有内容（支持非空目录）。"""
    target = resolve_path(path)
    if not os.path.isdir(target):
        raise NotADirectoryError(f"目录不存在：{target}")
    root = os.path.splitdrive(os.path.abspath(target))[0] or os.path.sep
    if target in (os.getcwd(), os.path.abspath(root)):
        raise ValueError(f"拒绝删除当前工作目录或磁盘根目录：{target}")
    shutil.rmtree(target)
    return f"已删除目录（含其全部内容）：{target}"


def delete_file(path: str | None = None, **_: object) -> str:
    """删除指定文件。"""
    target = resolve_path(path)
    if not os.path.exists(target):
        raise FileNotFoundError(f"路径不存在：{target}")
    if os.path.isdir(target):
        raise IsADirectoryError(f"这是目录而非文件，可改用 delete_dir：{target}")
    os.remove(target)
    return f"已删除文件：{target}"


def rename_path(path: str | None = None, new_name: str | None = None, **_: object) -> str:
    """更改文件或文件夹的名字（原地改名，不移动位置）。"""
    if not path:
        raise ValueError("缺少参数 path")
    if not new_name:
        raise ValueError("缺少参数 new_name")
    target = resolve_path(path)
    if not os.path.exists(target):
        raise FileNotFoundError(f"路径不存在：{target}")
    new_name = str(new_name).strip()
    if new_name in (".", ".."):
        raise ValueError("new_name 不能为空或为 . / ..")
    if any(char in new_name for char in ("/", "\\", ":")):
        raise ValueError(
            "new_name 只能是文件名或目录名，不能包含路径分隔符；本工具只改名，不移动位置"
        )
    dest = os.path.join(os.path.dirname(target), new_name)
    if os.path.normcase(dest) == os.path.normcase(target):
        return f"名字未发生变化：{target}"
    if os.path.exists(dest):
        raise FileExistsError(f"目标名称已存在：{dest}")
    os.rename(target, dest)
    kind = "目录" if os.path.isdir(dest) else "文件"
    return f"已将{kind}重命名：{target} -> {dest}"


def build_filesystem_tools() -> list[ToolSpec]:
    """构造文件系统类工具声明。"""
    return [
        ToolSpec(
            name="getcwd",
            description="获取当前工作目录",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=get_cwd,
        ),
        ToolSpec(
            name="list_dir",
            description="列出指定目录下所有文件和子目录，省略 path 时列出当前工作目录",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径，可为绝对或相对路径；省略时使用当前工作目录",
                    }
                },
                "required": [],
            },
            handler=list_dir,
        ),
        ToolSpec(
            name="get_file_type",
            description="获取指定文件的文件类型（扩展名、MIME 类型、文本或二进制）",
            parameters={
                "type": "object",
                "properties": {"path": dict(STR_PATH)},
                "required": ["path"],
            },
            handler=get_file_type,
        ),
        ToolSpec(
            name="read_file",
            description="获取指定文件的内容，仅支持纯文本格式文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": dict(STR_PATH),
                    "encoding": {
                        "type": "string",
                        "description": "文件编码，默认自动识别（utf-8/gbk）",
                    },
                },
                "required": ["path"],
            },
            handler=read_file,
        ),
        ToolSpec(
            name="create_file",
            description="根据指定的目录和文件名创建新文件",
            parameters={
                "type": "object",
                "properties": {
                    "dir": {"type": "string", "description": "文件所在目录，默认为当前工作目录"},
                    "filename": {"type": "string", "description": "文件名，例如 note.txt"},
                    "content": {"type": "string", "description": "文件内容，默认为空"},
                },
                "required": ["filename"],
            },
            handler=create_file,
        ),
        ToolSpec(
            name="edit_file",
            description=(
                "编辑指定文件的内容，仅支持纯文本格式文件。不传 old_text 时整体覆盖，"
                "传 old_text 时把其中的内容替换为 content"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": dict(STR_PATH),
                    "content": {"type": "string", "description": "新的文件内容"},
                    "old_text": {"type": "string", "description": "要被替换的原文片段，可选"},
                },
                "required": ["path", "content"],
            },
            handler=edit_file,
        ),
        ToolSpec(
            name="create_dir",
            description="创建新目录（包含多级目录）",
            parameters={
                "type": "object",
                "properties": {"path": dict(STR_PATH)},
                "required": ["path"],
            },
            handler=create_dir,
        ),
        ToolSpec(
            name="delete_dir",
            description="删除目录及其下所有内容（支持非空目录）",
            parameters={
                "type": "object",
                "properties": {"path": dict(STR_PATH)},
                "required": ["path"],
            },
            handler=delete_dir,
        ),
        ToolSpec(
            name="delete_file",
            description="删除指定文件",
            parameters={
                "type": "object",
                "properties": {"path": dict(STR_PATH)},
                "required": ["path"],
            },
            handler=delete_file,
        ),
        ToolSpec(
            name="rename_path",
            description="更改文件或文件夹的名字（原地改名，不移动位置）",
            parameters={
                "type": "object",
                "properties": {
                    "path": dict(STR_PATH),
                    "new_name": {
                        "type": "string",
                        "description": (
                            "新的名字，只能是文件名或目录名，不能包含路径分隔符，"
                            "例如 report.txt 或 图片素材"
                        ),
                    },
                },
                "required": ["path", "new_name"],
            },
            handler=rename_path,
        ),
    ]


__all__ = [
    "build_filesystem_tools",
    "create_dir",
    "create_file",
    "delete_dir",
    "delete_file",
    "edit_file",
    "get_cwd",
    "get_file_type",
    "list_dir",
    "read_file",
    "rename_path",
]
