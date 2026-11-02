"""文本处理工具函数。"""

from __future__ import annotations

import json
import locale
import re
from typing import Any

# 部分服务商会在正文里混入 ``</tool_call>`` 之类的模板碎片，
# 这里统一清理掉（零宽字符一并处理）。
_TEMPLATE_MARKER = re.compile(r"</[\u200b\u200c\u200d\ufeff]*tool_call\s*>", re.IGNORECASE)


def strip_template_fragments(text: str) -> str:
    """移除正文中的模板碎片。

    只在检测到 ``</tool_call>`` 标记时才会顺带清理其前后的残缺花括号，
    避免误伤正常的代码片段。
    """
    if not text or not _TEMPLATE_MARKER.search(text):
        return text
    cleaned = _TEMPLATE_MARKER.sub("", text)
    return re.sub(r"[{}]?\s*$", "", cleaned)


def strip_tool_call_tail(text: str) -> str:
    """去掉工具调用轮次里服务商泄漏的 JSON 残片。

    部分服务商会把工具调用的 JSON 尾巴（通常是 ``}``）混进正文，
    仅在"本轮以工具调用结束"时调用，避免误伤正常文本。
    """
    cleaned = text.rstrip()
    if cleaned.endswith("}"):
        cleaned = cleaned[:-1].rstrip()
    return cleaned



def decode_console(raw: bytes) -> str:
    """按多种编码尝试解码控制台/子进程输出。"""
    for encoding in (locale.getpreferredencoding(False), "mbcs", "gbk", "utf-8"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _decode_object(decoder: json.JSONDecoder, text: str) -> dict[str, Any] | None:
    """尝试解析一个 JSON 对象，失败返回 ``None``。"""
    try:
        obj, _ = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# 流式参数常在末尾被截断，按顺序尝试补齐这些右括号/引号
_REPAIR_SUFFIXES = ('"}', "}}", '"}}')


def parse_json_object(raw: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """从（可能被截断或带碎片的）JSON 文本中解析出第一个完整对象。

    流式返回的参数常见几种畸形：
    - 尾部多出 ``}}`` 或 ``</tool_call>`` 之类的碎片；
    - 末尾被截断，缺少右括号；
    - 整段工具调用被塞进参数里（``{"name": ..., "arguments": {...}}``）。

    这里从左到右尝试每个 ``{`` 作为起点：先用 ``raw_decode`` 取第一个能解析成功的
    对象；若失败，再尝试补齐缺失的右括号后重试。

    返回 ``(对象, 错误信息)``：解析成功时错误为 ``None``，失败时对象为 ``None``。
    """
    text = (raw or "").strip()
    if not text:
        return {}, None

    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        candidate = text[start:]
        obj = _decode_object(decoder, candidate)
        if obj is not None:
            return obj, None
        for suffix in _REPAIR_SUFFIXES:
            obj = _decode_object(decoder, candidate + suffix)
            if obj is not None:
                return obj, None
    return None, f"参数 JSON 解析失败，原始参数：{truncate(text, 200)}"


def truncate(text: str, limit: int = 200, suffix: str = "...") -> str:
    """截断过长的文本。"""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + suffix


def unwrap_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """兼容"整段工具调用被包一层"的参数格式。

    部分服务商会把 ``{"name": "x", "arguments": {...}}`` 整体当成参数字符串传回来，
    此时真正的参数在 ``arguments`` 字段里。
    """
    inner = arguments.get("arguments")
    if isinstance(inner, dict) and isinstance(arguments.get("name"), str):
        return inner
    return arguments
