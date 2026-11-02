"""文件系统相关的通用辅助函数（供文件工具复用）。"""

from __future__ import annotations

import locale
import os
from collections.abc import Iterable

from core.utils.text import decode_console  # noqa: F401  (统一出口)

ENCODING_CANDIDATES: tuple[str, ...] = ("utf-8", "gbk")


def resolve_path(path: str | os.PathLike[str] | None, base: str | None = None) -> str:
    """把路径转成绝对路径，支持 ``~`` 与环境变量展开。

    相对路径基于 ``base``（默认当前工作目录）解析。
    """
    if path is None or str(path).strip() == "":
        raise ValueError("缺少参数 path")
    raw = os.path.expandvars(os.path.expanduser(str(path).strip()))
    if not os.path.isabs(raw):
        raw = os.path.join(base or os.getcwd(), raw)
    return os.path.abspath(raw)


def is_text_file(path: str) -> bool:
    """粗略判断文件是否为纯文本（首块是否包含 NUL 字节）。"""
    with open(path, "rb") as handle:
        chunk = handle.read(8192)
    return b"\x00" not in chunk


def _encoding_chain(encoding: str | None) -> Iterable[str]:
    if encoding:
        yield encoding
    yield from ENCODING_CANDIDATES
    preferred = locale.getpreferredencoding(False)
    if preferred:
        yield preferred


def read_text_file(path: str, encoding: str | None = None) -> str:
    """读取纯文本文件，自动尝试常见编码。"""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在：{path}")
    if not is_text_file(path):
        raise ValueError("仅支持纯文本格式文件，该文件疑似二进制文件")
    with open(path, "rb") as handle:
        raw = handle.read()
    for candidate in _encoding_chain(encoding):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("无法识别文件编码，请指定 encoding 参数")
