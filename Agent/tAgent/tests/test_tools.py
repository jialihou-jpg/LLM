"""工具注册中心与内置工具的测试。"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys

import pytest

from core.factory import build_default_registry
from core.tools.base import ToolSpec
from core.tools.builtin import cli_tools
from core.tools.registry import ToolRegistry


def test_default_registry_contains_all_builtin_tools() -> None:
    registry = build_default_registry()
    assert len(registry) == 15
    assert "read_file" in registry
    assert "isLeapYear" in registry
    assert "searchweb" in registry
    assert "fetchweb" in registry
    assert "RunCli" in registry


def test_schemas_are_openai_compatible() -> None:
    registry = build_default_registry()
    schemas = registry.schemas()
    assert all(item["type"] == "function" for item in schemas)
    assert all("name" in item["function"] for item in schemas)
    assert all("parameters" in item["function"] for item in schemas)


def test_call_unknown_tool_returns_failure() -> None:
    registry = build_default_registry()
    result = registry.call("not_exists", {})
    assert result.ok is False
    assert "未知的工具" in result.error


def test_call_tool_with_exception_is_captured() -> None:
    def boom(**_: object) -> str:
        raise RuntimeError("炸了")

    registry = ToolRegistry(
        [ToolSpec(name="boom", description="会抛异常", parameters={}, handler=boom)]
    )
    result = registry.call("boom", {})
    assert result.ok is False
    assert "炸了" in result.error


def test_validate_missing_required_parameter() -> None:
    registry = build_default_registry()
    result = registry.call("isLeapYear", {})
    assert result.ok is False
    assert "缺少参数 year" in result.error


def test_validate_coerces_integer_string() -> None:
    registry = build_default_registry()
    result = registry.call("isLeapYear", {"year": "2024"})
    assert result.ok is True
    assert "2024年是闰年" in result.output


def test_validate_drops_unknown_parameters() -> None:
    registry = build_default_registry()
    result = registry.call("list_dir", {"path": ".", "unexpected": "x"})
    assert result.ok is True


def test_list_dir_defaults_to_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "hello.txt").write_text("x", encoding="utf-8")
    registry = build_default_registry()
    result = registry.call("list_dir", {})
    assert result.ok is True
    assert "hello.txt" in result.output


def test_filesystem_tools_roundtrip(tmp_path) -> None:
    registry = build_default_registry()

    created = registry.call(
        "create_file",
        {"dir": str(tmp_path), "filename": "a.txt", "content": "hello"},
    )
    assert created.ok is True

    read = registry.call("read_file", {"path": str(tmp_path / "a.txt")})
    assert "hello" in read.output

    edited = registry.call(
        "edit_file",
        {"path": str(tmp_path / "a.txt"), "content": "world", "old_text": "hello"},
    )
    assert edited.ok is True
    assert "world" in registry.call("read_file", {"path": str(tmp_path / "a.txt")}).output

    renamed = registry.call("rename_path", {"path": str(tmp_path / "a.txt"), "new_name": "b.txt"})
    assert renamed.ok is True
    assert os.path.exists(tmp_path / "b.txt")

    deleted = registry.call("delete_file", {"path": str(tmp_path / "b.txt")})
    assert deleted.ok is True


def test_delete_dir_refuses_current_directory() -> None:
    registry = build_default_registry()
    result = registry.call("delete_dir", {"path": os.getcwd()})
    assert result.ok is False


# ---------------------------------------------------------------- RunCli
# 核心行为直接测同步函数 run_cli；与注册中心的接线通过 acall 验证。

def test_run_cli_success_returns_stdout_and_exit_code() -> None:
    output = cli_tools.run_cli(sys.executable, ["-c", "print('hello runcli')"])
    assert "退出码：0" in output
    assert "hello runcli" in output
    assert "标准错误" in output


def test_run_cli_returns_stderr_and_nonzero_exit_code() -> None:
    output = cli_tools.run_cli(
        sys.executable, ["-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"]
    )
    assert "退出码：3" in output
    assert "boom" in output


def test_run_cli_missing_command_raises() -> None:
    with pytest.raises(ValueError, match="缺少参数 command"):
        cli_tools.run_cli("   ")


def test_run_cli_unknown_program_reports_exit_code_127() -> None:
    output = cli_tools.run_cli("tagent_command_that_does_not_exist")
    assert "退出码：127" in output
    assert "找不到可执行程序" in output
    if os.name == "nt":
        # Windows 提示应包含对已移除旧工具（如 wmic）的替代方案
        assert "powershell" in output


def test_run_cli_args_without_shell_metacharacters(tmp_path) -> None:
    # shell=False 时重定向符号应被原样当作普通参数，而不会真的创建文件
    target = tmp_path / "should_not_exist.txt"
    output = cli_tools.run_cli(
        sys.executable, ["-c", "import sys; print(sys.argv[1:])", ">", str(target)]
    )
    assert "退出码：0" in output
    assert str(target) in output
    assert not target.exists()


def test_run_cli_truncates_long_output(monkeypatch) -> None:
    monkeypatch.setattr(cli_tools, "MAX_OUTPUT_CHARS", 50)
    output = cli_tools.run_cli(sys.executable, ["-c", "print('x' * 1000)"])
    assert "已截断" in output
    assert "原始 1000 字符" in output


def test_run_cli_timeout_reports_exit_code_124(monkeypatch) -> None:
    monkeypatch.setattr(cli_tools, "DEFAULT_TIMEOUT", 1)
    output = cli_tools.run_cli(sys.executable, ["-c", "import time; time.sleep(10)"])
    assert "退出码：124" in output
    assert "超时" in output


def test_run_cli_accepts_string_args_and_splits_them() -> None:
    # 模型把 args 拼成一个字符串时，应自动拆成多个参数
    output = cli_tools.run_cli(sys.executable, "-c \"import sys; print(sys.argv[1:])\" alpha beta")
    assert "退出码：0" in output
    assert "['alpha', 'beta']" in output


def test_run_cli_string_args_keeps_windows_path_backslashes(tmp_path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("payload", encoding="utf-8")
    output = cli_tools.run_cli(sys.executable, f"-c \"import sys; print(sys.argv[1])\" {target}")
    assert "退出码：0" in output
    assert str(target) in output


def test_run_cli_registry_acall_accepts_string_args() -> None:
    # 注册中心对 array/string 复合类型放行后，字符串 args 也能正常执行
    registry = build_default_registry()
    result = asyncio.run(
        registry.acall("RunCli", {"command": sys.executable, "args": "--version"})
    )
    assert result.ok is True
    assert "退出码：0" in result.output


def test_run_cli_registry_missing_command_fails_validation() -> None:
    registry = build_default_registry()
    result = asyncio.run(registry.acall("RunCli", {"args": ["--version"]}))
    assert result.ok is False
    assert "缺少参数 command" in result.error


def test_run_cli_registered_handler_is_async_non_blocking() -> None:
    # 注册的处理器应为异步函数（内部用线程执行，避免阻塞前端事件循环）
    tool = build_default_registry().get("RunCli")
    assert tool is not None
    assert inspect.iscoroutinefunction(tool.handler)
