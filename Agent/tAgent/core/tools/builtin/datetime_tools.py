"""日期与计算类工具。"""

from __future__ import annotations

import os
import subprocess

from core.tools.base import ToolSpec
from core.utils.text import decode_console


def getdate(**_: object) -> str:
    """获取当前电脑的日期和时间（调用本地 date / time 命令）。"""
    command = "date /t & time /t" if os.name == "nt" else "date '+%Y-%m-%d %H:%M:%S'"
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    text = decode_console(proc.stdout).strip()
    if proc.returncode != 0:
        error = decode_console(proc.stderr).strip()
        raise RuntimeError(error or "调用本地 date 命令失败")
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def is_leap_year(year: int | None = None, **_: object) -> str:
    """判断指定年份是不是闰年。"""
    if year is None:
        raise ValueError("缺少参数 year")
    year = int(year)
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    return f"{year}年{'是' if leap else '不是'}闰年"


def build_datetime_tools() -> list[ToolSpec]:
    """构造日期与计算类工具声明。"""
    return [
        ToolSpec(
            name="getdate",
            description="获取当前电脑的日期和时间",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=getdate,
        ),
        ToolSpec(
            name="isLeapYear",
            description="判断指定年份是不是闰年",
            parameters={
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "要判断的年份，例如 2024"}
                },
                "required": ["year"],
            },
            handler=is_leap_year,
        ),
    ]


__all__ = ["build_datetime_tools", "getdate", "is_leap_year"]
