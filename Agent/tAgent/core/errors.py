"""核心层异常定义。

所有异常都继承自 :class:`AgentError`，前端只需捕获这一个基类即可，
无需知道底层是网络错误、配置错误还是工具错误。
"""

from __future__ import annotations


class AgentError(Exception):
    """所有核心层异常的基类。"""


class ConfigurationError(AgentError):
    """配置缺失或非法（缺少 base_url / api_key / model 等）。"""


class LLMError(AgentError):
    """调用大模型服务失败（网络、鉴权、协议解析等）。"""


class ToolError(AgentError):
    """工具执行失败。"""

    def __init__(self, message: str, *, tool_name: str = "") -> None:
        super().__init__(message)
        self.tool_name = tool_name
