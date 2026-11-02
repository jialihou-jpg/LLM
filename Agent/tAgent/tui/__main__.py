"""命令行入口：``python -m tui``。"""

from __future__ import annotations

import argparse
import sys

from core.config import load_settings
from core.errors import ConfigurationError
from tui.app import TAgentApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tagent-tui",
        description="tAgent —— 基于 Textual 的终端智能体界面",
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        default=None,
        help="配置文件路径（默认按 core.config 的优先级自动查找）",
    )
    parser.add_argument(
        "--model",
        dest="model",
        default=None,
        help="覆盖配置中的模型名称",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        default=None,
        help="覆盖配置中的服务地址",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings(args.config)
    except ConfigurationError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        return 2

    settings = settings.with_overrides(
        llm_model=args.model, llm_base_url=args.base_url
    )
    TAgentApp(settings=settings).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
