"""通用工具函数的测试。"""

from __future__ import annotations

from core.utils.text import (
    parse_json_object,
    strip_template_fragments,
    strip_tool_call_tail,
    unwrap_tool_arguments,
)


def test_parse_json_object_plain() -> None:
    obj, error = parse_json_object('{"path": "a.txt"}')
    assert error is None
    assert obj == {"path": "a.txt"}


def test_parse_json_object_with_trailing_garbage() -> None:
    obj, error = parse_json_object('{"path": "a.txt"}}\n</tool_call>')
    assert error is None
    assert obj == {"path": "a.txt"}


def test_parse_json_object_empty_returns_empty_dict() -> None:
    obj, error = parse_json_object("")
    assert error is None
    assert obj == {}


def test_parse_json_object_invalid_returns_error() -> None:
    obj, error = parse_json_object("{不是 json")
    assert obj is None
    assert error is not None
    assert "解析失败" in error


def test_parse_json_object_finds_nested_object() -> None:
    """双层花括号包裹时，也能取到内层完整对象。"""
    obj, error = parse_json_object('{{"name": "isLeapYear", "arguments": {"year": 2024}}}')
    assert error is None
    assert obj == {"name": "isLeapYear", "arguments": {"year": 2024}}


def test_parse_json_object_repairs_truncated_tail() -> None:
    """末尾被截断时，补齐右括号后仍能取到完整对象。"""
    obj, error = parse_json_object('{{"name": "isLeapYear", "arguments": {"year": 2024}')
    assert error is None
    assert obj == {"name": "isLeapYear", "arguments": {"year": 2024}}


def test_parse_json_object_repairs_truncated_string() -> None:
    obj, error = parse_json_object('{"path": "a.txt')
    assert error is None
    assert obj == {"path": "a.txt"}


def test_unwrap_tool_arguments_extracts_inner_payload() -> None:
    wrapped = {"name": "isLeapYear", "arguments": {"year": 2024}}
    assert unwrap_tool_arguments(wrapped) == {"year": 2024}


def test_unwrap_tool_arguments_keeps_plain_payload() -> None:
    plain = {"year": 2024}
    assert unwrap_tool_arguments(plain) == {"year": 2024}


def test_strip_template_fragments_removes_marker() -> None:
    assert strip_template_fragments("正文</tool_call>") == "正文"


def test_strip_template_fragments_keeps_normal_text() -> None:
    assert strip_template_fragments('{"a": 1}') == '{"a": 1}'


def test_strip_tool_call_tail_removes_leaked_brace() -> None:
    assert strip_tool_call_tail("看看结果 }") == "看看结果"
    assert strip_tool_call_tail("正常结束") == "正常结束"
