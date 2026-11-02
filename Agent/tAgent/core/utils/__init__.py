"""核心层通用工具函数。"""

from __future__ import annotations

from core.utils.files import is_text_file, read_text_file, resolve_path
from core.utils.text import (
    decode_console,
    parse_json_object,
    strip_template_fragments,
    truncate,
)

__all__ = [
    "decode_console",
    "is_text_file",
    "parse_json_object",
    "read_text_file",
    "resolve_path",
    "strip_template_fragments",
    "truncate",
]
