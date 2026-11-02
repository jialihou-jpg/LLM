"""tAgent 的 Textual 终端界面。

本包只负责"怎么展示"：把 :mod:`core` 产出的事件渲染成终端界面。
所有业务逻辑都在 :mod:`core` 中，前端不直接调用模型服务或工具。
"""

from __future__ import annotations

from tui.app import TAgentApp

__all__ = ["TAgentApp"]
