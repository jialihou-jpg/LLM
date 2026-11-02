"""TUI 内置斜杠命令。

命令属于界面层能力（只影响当前前端会话），因此放在 ``tui`` 而不是 ``core``。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅用于类型检查
    from tui.app import TAgentApp


@dataclass(frozen=True, slots=True)
class Command:
    """一条斜杠命令。"""

    name: str
    description: str
    handler: Callable[[TAgentApp, str], None]


def _cmd_help(app: TAgentApp, _args: str) -> None:
    lines = ["可用命令："]
    for command in COMMANDS:
        lines.append(f"  /{command.name:<8} {command.description}")
    app.query_one("ChatLog").add_info("\n".join(lines))


def _cmd_clear(app: TAgentApp, _args: str) -> None:
    app.clear_conversation()


def _cmd_tools(app: TAgentApp, _args: str) -> None:
    names = app.agent.registry.names() if app.agent else []
    app.query_one("ChatLog").add_info(f"已注册工具（{len(names)}）：\n" + ", ".join(names))


def _cmd_model(app: TAgentApp, _args: str) -> None:
    model = app.settings.llm.model if app.settings else "-"
    app.query_one("ChatLog").add_info(f"当前模型：{model}")


def _cmd_cwd(app: TAgentApp, _args: str) -> None:
    app.query_one("ChatLog").add_info(f"当前工作目录：{os.getcwd()}")


def _cmd_exit(app: TAgentApp, _args: str) -> None:
    app.exit()


COMMANDS: tuple[Command, ...] = (
    Command("help", "查看可用命令", _cmd_help),
    Command("clear", "清空对话记录", _cmd_clear),
    Command("tools", "列出已注册的工具", _cmd_tools),
    Command("model", "显示当前模型", _cmd_model),
    Command("cwd", "显示当前工作目录", _cmd_cwd),
    Command("exit", "退出 tAgent", _cmd_exit),
)

_BY_NAME: dict[str, Command] = {command.name: command for command in COMMANDS}


def dispatch(app: TAgentApp, line: str) -> bool:
    """解析并执行一条斜杠命令；未识别时返回 ``False``。"""
    body = line.lstrip("/").strip()
    if not body:
        return False
    name, _, args = body.partition(" ")
    command = _BY_NAME.get(name.lower())
    if command is None:
        app.query_one("ChatLog").add_info(f"未知命令：/{name}，输入 /help 查看可用命令")
        return True
    command.handler(app, args.strip())
    return True
