"""配置加载。

配置来源优先级（从高到低）：

1. 显式传入的配置文件路径
2. 环境变量 ``TAGENT_CONFIG`` 指向的配置文件
3. 当前工作目录下的 ``config.ini``
4. 项目根目录（tAgent/）下的 ``config.ini``
5. 用户目录下的 ``~/.tagent/config.ini``

环境变量 ``TAGENT_BASE_URL`` / ``TAGENT_API_KEY`` / ``TAGENT_MODEL`` 可覆盖
配置文件中的同名字段，便于 CI 与容器部署；``TAGENT_SEARCH_API_KEY`` 可覆盖
``[search]`` 段的百度千帆搜索 API Key。
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from core.errors import ConfigurationError
from core.prompts import DEFAULT_SYSTEM_PROMPT

CONFIG_FILENAME = "config.ini"
ENV_CONFIG_PATH = "TAGENT_CONFIG"
ENV_BASE_URL = "TAGENT_BASE_URL"
ENV_API_KEY = "TAGENT_API_KEY"
ENV_MODEL = "TAGENT_MODEL"
ENV_SEARCH_API_KEY = "TAGENT_SEARCH_API_KEY"

SEARCH_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"
SEARCH_DEFAULT_EDITION = "standard"
SEARCH_EDITIONS = ("standard", "turbo", "pro")

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """大模型服务相关配置。"""

    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0

    @property
    def chat_completions_url(self) -> str:
        """完整的 chat/completions 地址。"""
        return f"{self.base_url.rstrip('/')}/chat/completions"


@dataclass(frozen=True, slots=True)
class SearchSettings:
    """百度千帆「AI 搜索 - 网页搜索」相关配置。

    对应 ``POST /v2/ai_search/web_search`` 接口：只返回网页搜索结果，
    不调用大模型生成摘要，每月有 1500 次免费额度（按天发放）。

    ``api_key`` 为空时搜索工具依然会注册，但调用时会向模型返回明确的
    "未配置" 错误，而不是让整个应用启动失败。
    """

    api_key: str = ""
    edition: str = SEARCH_DEFAULT_EDITION
    endpoint: str = SEARCH_ENDPOINT
    timeout: float = 90.0
    top_k: int = 10


@dataclass(frozen=True, slots=True)
class Settings:
    """应用级配置。"""

    llm: LLMSettings
    max_tool_rounds: int = 10
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    search: SearchSettings = field(default_factory=SearchSettings)
    config_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def with_overrides(self, **kwargs: Any) -> Settings:
        """返回应用了覆盖项的新配置对象（配置对象本身不可变）。"""
        llm_overrides = {
            key[4:]: value
            for key, value in kwargs.items()
            if key.startswith("llm_") and value is not None
        }
        other = {key: value for key, value in kwargs.items() if not key.startswith("llm_")}
        llm = replace(self.llm, **llm_overrides) if llm_overrides else self.llm
        return replace(self, llm=llm, **other)


def find_config_file(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """按优先级查找配置文件，返回第一个存在的路径。

    显式指定的路径若不存在会直接报错，避免"配置写错路径却悄悄用了别的配置"。
    """
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigurationError(f"指定的配置文件不存在：{path}")
        return path.resolve()

    candidates: list[Path] = []
    env_path = os.environ.get(ENV_CONFIG_PATH)
    if env_path:
        env_file = Path(env_path).expanduser()
        if not env_file.is_file():
            raise ConfigurationError(f"环境变量 {ENV_CONFIG_PATH} 指向的配置文件不存在：{env_file}")
        return env_file.resolve()
    candidates.append(Path.cwd() / CONFIG_FILENAME)
    candidates.append(_PACKAGE_ROOT / CONFIG_FILENAME)
    candidates.append(Path.home() / ".tagent" / CONFIG_FILENAME)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    try:
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except OSError as exc:  # pragma: no cover - 依赖文件系统状态
        raise ConfigurationError(f"无法读取配置文件 {path}：{exc}") from exc
    except configparser.Error as exc:
        raise ConfigurationError(f"配置文件格式错误 {path}：{exc}") from exc
    return parser


def _require(section: configparser.SectionProxy, key: str, path: Path) -> str:
    try:
        value = section[key].strip()
    except KeyError as exc:
        raise ConfigurationError(f"配置文件 {path} 缺少配置项：[{section.name}] {key}") from exc
    if not value:
        raise ConfigurationError(f"配置文件 {path} 的配置项为空：[{section.name}] {key}")
    return value


def _optional(section: Any, *keys: str) -> str:
    """按顺序读取第一个非空配置项；不存在时返回空字符串。"""
    for key in keys:
        try:
            value = section[key]
        except (KeyError, TypeError):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def load_settings(path: str | os.PathLike[str] | None = None) -> Settings:
    """加载配置；找不到配置文件或缺少必要字段时抛出 :class:`ConfigurationError`。"""
    config_path = find_config_file(path)
    if config_path is None:
        candidates = (Path.cwd() / CONFIG_FILENAME, _PACKAGE_ROOT / CONFIG_FILENAME)
        searched = ", ".join(str(item) for item in candidates)
        raise ConfigurationError(
            "未找到配置文件 config.ini，请复制 config.example.ini 并填写必要信息。\n"
            f"已查找：{searched}"
        )

    parser = _read_ini(config_path)
    if not parser.has_section("llm"):
        raise ConfigurationError(f"配置文件 {config_path} 缺少 [llm] 段落")

    llm_section = parser["llm"]
    base_url = os.environ.get(ENV_BASE_URL) or _require(llm_section, "base_url", config_path)
    api_key = os.environ.get(ENV_API_KEY) or _require(llm_section, "api_key", config_path)
    model = os.environ.get(ENV_MODEL) or _require(llm_section, "model", config_path)

    timeout = 60.0
    agent_section = parser["agent"] if parser.has_section("agent") else {}
    raw_timeout = agent_section.get("timeout") or llm_section.get("timeout")
    if raw_timeout:
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ConfigurationError(f"配置项 timeout 必须是数字：{raw_timeout}") from exc

    max_rounds = 10
    raw_rounds = agent_section.get("max_tool_rounds")
    if raw_rounds:
        try:
            max_rounds = int(raw_rounds)
        except ValueError as exc:
            raise ConfigurationError(f"配置项 max_tool_rounds 必须是整数：{raw_rounds}") from exc

    system_prompt = agent_section.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

    search_section = parser["search"] if parser.has_section("search") else {}
    search_api_key = os.environ.get(ENV_SEARCH_API_KEY) or _optional(
        search_section,
        "baidu_qianfan_api_key",
        "baidu_qianfan_key",
        "api_key",
    )
    search_edition = (
        _optional(search_section, "edition", "baidu_qianfan_edition")
        or SEARCH_DEFAULT_EDITION
    )
    if search_edition not in SEARCH_EDITIONS:
        raise ConfigurationError(
            f"配置项 [search] edition 必须是 {'/'.join(SEARCH_EDITIONS)} 之一：{search_edition}"
        )
    search_endpoint = _optional(search_section, "endpoint") or SEARCH_ENDPOINT

    search_timeout = 90.0
    raw_search_timeout = _optional(search_section, "timeout")
    if raw_search_timeout:
        try:
            search_timeout = float(raw_search_timeout)
        except ValueError as exc:
            raise ConfigurationError(
                f"配置项 [search] timeout 必须是数字：{raw_search_timeout}"
            ) from exc

    search_top_k = 10
    raw_top_k = _optional(search_section, "top_k")
    if raw_top_k:
        try:
            search_top_k = int(raw_top_k)
        except ValueError as exc:
            raise ConfigurationError(f"配置项 [search] top_k 必须是整数：{raw_top_k}") from exc
        if not 1 <= search_top_k <= 20:
            raise ConfigurationError(f"配置项 [search] top_k 必须在 1~20 之间：{raw_top_k}")

    return Settings(
        llm=LLMSettings(base_url=base_url, api_key=api_key, model=model, timeout=timeout),
        max_tool_rounds=max_rounds,
        system_prompt=system_prompt,
        search=SearchSettings(
            api_key=search_api_key,
            edition=search_edition,
            endpoint=search_endpoint,
            timeout=search_timeout,
            top_k=search_top_k,
        ),
        config_path=config_path,
    )
