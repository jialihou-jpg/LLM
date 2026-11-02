"""本地命令行（CLI）调用工具（只依赖 Python 标准库）。

教学用途：让 Agent 通过 :func:`subprocess.run` 调用本机已安装的任意命令行程序，
程序名与参数以列表形式传入、``shell=False`` 执行，不拼接 shell 命令字符串。
执行结果（标准输出、标准错误、退出码）统一格式化后回传给模型，
由模型判断成功与否并决定下一步。

同步核心函数 :func:`run_cli` 保持简单、便于教学阅读；注册到工具中心的
:func:`run_cli_async` 用 :func:`asyncio.to_thread` 把阻塞式子进程调用放到
工作线程，避免长时间运行的命令卡住 TUI / Web 前端的事件循环。

注意：本阶段不做白名单 / 黑名单 / 审批，命令以运行 tAgent 的当前用户权限执行，
只能在受控的教学实验环境中使用。
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from collections.abc import Sequence

from core.tools.base import ToolSpec
from core.utils.text import decode_console

# 单次命令执行的最长时间（秒），超时后子进程会被自动终止
DEFAULT_TIMEOUT = 60.0
# 每一路输出（stdout / stderr）最多回传给模型的字符数，超出部分截断
MAX_OUTPUT_CHARS = 8000

# 约定俗成的退出码：124 与 GNU timeout 一致，126/127 与 shell 一致
EXIT_TIMEOUT = 124
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127


def run_cli(
    command: str | None = None,
    args: str | Sequence[str] | None = None,
    **_: object,
) -> str:
    """执行本地命令行程序，返回 stdout / stderr / 退出码组成的文本。"""
    if not command or not str(command).strip():
        raise ValueError("缺少参数 command")

    arguments = _normalize_args(args)
    # 程序名与参数拼装为列表，通过 shell=False 执行，避免 shell 注入
    argv = [str(command).strip(), *arguments]

    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_partial(getattr(exc, "stdout", None))
        stderr = _decode_partial(getattr(exc, "stderr", None))
        return _format_result(
            argv,
            EXIT_TIMEOUT,
            stdout,
            stderr,
            note=f"命令执行超时（超过 {DEFAULT_TIMEOUT:g} 秒，已被终止）",
        )
    except FileNotFoundError:
        return _format_result(argv, EXIT_NOT_FOUND, "", _not_found_message(argv[0]))
    except OSError as exc:
        return _format_result(
            argv,
            EXIT_NOT_EXECUTABLE,
            "",
            f"无法启动程序 {argv[0]}：{exc}",
        )

    return _format_result(
        argv,
        proc.returncode,
        decode_console(proc.stdout),
        decode_console(proc.stderr),
    )


async def run_cli_async(
    command: str | None = None,
    args: str | Sequence[str] | None = None,
    **_: object,
) -> str:
    """:func:`run_cli` 的异步包装：在线程中执行子进程，不阻塞事件循环。"""
    return await asyncio.to_thread(run_cli, command=command, args=args)


def _normalize_args(args: str | Sequence[str] | None) -> list[str]:
    """把模型传来的 args 归一化为字符串列表。

    规范用法是数组（如 ``["-la", "/tmp"]``）；但不少模型会把参数拼成一个
    字符串（如 ``"-la /tmp"``），此时按所在平台的命令行规则自动拆分，
    避免工具直接报"参数类型不正确"。
    """
    if args is None:
        return []
    if isinstance(args, str):
        return _split_args(args)
    if isinstance(args, (list, tuple)):
        return [str(arg) for arg in args]
    raise ValueError("参数 args 必须是字符串数组，或一个可按空格拆分的字符串")


def _split_args(text: str) -> list[str]:
    """把单个参数字符串拆成列表（按平台选择分词规则）。"""
    text = text.strip()
    if not text:
        return []
    if os.name == "nt":
        return _split_windows_cmdline(text)
    try:
        return shlex.split(text)
    except ValueError:
        # 引号不配对等情况下退化为朴素空白拆分
        return text.split()


def _split_windows_cmdline(text: str) -> list[str]:
    """Windows 命令行分词：按空白分段，双引号可包裹含空格的参数。

    与 :func:`shlex.split` 的 POSIX 模式不同，这里不把反斜杠当转义符，
    否则 ``C:\\Users\\...`` 这样的路径会被拆坏；单引号在 cmd 中不是引号。
    """
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
        elif char.isspace() and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _not_found_message(program: str) -> str:
    """程序找不到时，按平台给出可操作的中文提示。"""
    if os.name == "nt":
        return (
            f"找不到可执行程序：{program}，请确认程序已安装且名称/路径正确。"
            "若是 dir、cd、echo 等 cmd 内置命令，或 npm、pip 这类以 .cmd/.bat "
            "形式安装的程序，请改用 command='cmd'、args=['/c', '实际命令'] 调用；"
            "若是 wmic 等在新版 Windows 中已被移除的旧工具，请改用 "
            "command='powershell'、args=['-NoProfile', '-Command', '等价 PowerShell 命令']，"
            "例如用 Get-CimInstance 替代 wmic 查询"
        )
    return (
        f"找不到可执行程序：{program}，请确认程序已安装且名称/路径正确。"
        "若是 cd、export 等 shell 内置命令，请改用 command='sh'、"
        "args=['-c', '实际命令'] 调用"
    )


def _decode_partial(raw: object) -> str:
    """解码超时时已捕获的部分输出（可能为 bytes、str 或不存在）。"""
    if isinstance(raw, bytes):
        return decode_console(raw)
    return raw if isinstance(raw, str) else ""


def _truncate(text: str, limit: int | None = None) -> tuple[str, str]:
    """截断过长文本，返回 (截断后的文本, 截断说明)；未截断时说明为空串。"""
    if limit is None:
        limit = MAX_OUTPUT_CHARS
    if len(text) <= limit:
        return text, ""
    omitted = len(text) - limit
    note = f"（内容过长已截断：原始 {len(text)} 字符，仅保留前 {limit} 字符，省略 {omitted} 字符）"
    return text[:limit], note


def _format_result(
    argv: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
    note: str = "",
) -> str:
    """把执行结果格式化成模型易读的文本。"""
    stdout = stdout.strip()
    stderr = stderr.strip()
    stdout_text, stdout_note = _truncate(stdout)
    stderr_text, stderr_note = _truncate(stderr)

    lines = [
        f"命令：{' '.join(argv)}",
        f"退出码：{returncode}" + (f"（{note}）" if note else ""),
        f"标准输出{stdout_note}：",
        stdout_text or "（空）",
        f"标准错误{stderr_note}：",
        stderr_text or "（空）",
    ]
    return "\n".join(lines)


def build_cli_tools() -> list[ToolSpec]:
    """构造本地命令行调用工具声明。"""
    return [
        ToolSpec(
            name="RunCli",
            description=(
                "执行本地已安装的命令行程序（CLI），返回标准输出、标准错误和退出码，"
                "可根据退出码是否为 0 判断执行是否成功。"
                "典型用途：查询本机硬件与系统信息（内存、CPU、磁盘、系统版本、IP、进程）、"
                "运行 python/git 等已安装的程序、执行脚本。"
                "command 是程序名或可执行文件路径，args 是按顺序传递的参数列表；"
                "命令不经过 shell，因此 command 必须是真实的可执行文件（如 python、git），"
                "不能直接使用 shell 内置命令或管道、重定向："
                "Windows 下需要 shell 时可用 command='cmd'、args=['/c', '命令字符串']，"
                "类 Unix 下可用 command='sh'、args=['-c', '命令字符串']。"
                "Windows 查询系统信息优先用 PowerShell（不要用新版 Windows 已移除的 wmic），"
                "例如查物理内存：command='powershell'、"
                "args=['-NoProfile', '-Command', "
                "'Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed']。"
                "args 必须简短，不要内联多行或很长的脚本；复杂脚本应先用文件工具写成"
                " .ps1/.py/.sh 文件再执行；也不要用本工具下载网页，抓网页请用 fetchweb。"
                f"命令执行超过 {DEFAULT_TIMEOUT:g} 秒会被终止，过长的输出会被截断并标明。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的程序名称或可执行文件路径，例如 python、git、ipconfig",
                    },
                    "args": {
                        # 数组是规范形式；兼容部分模型把参数拼成一个字符串的情况
                        "type": ["array", "string"],
                        "items": {"type": "string"},
                        "description": (
                            "按顺序传递给程序的命令行参数，推荐使用数组，"
                            "例如 ['--version'] 或 ['config', 'list']，每个参数一个元素；"
                            "若传成一个字符串（如 'config list'）会自动按空格拆分"
                        ),
                    },
                },
                "required": ["command"],
            },
            handler=run_cli_async,
        )
    ]


__all__ = [
    "DEFAULT_TIMEOUT",
    "MAX_OUTPUT_CHARS",
    "build_cli_tools",
    "run_cli",
    "run_cli_async",
]
