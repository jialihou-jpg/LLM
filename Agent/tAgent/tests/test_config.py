"""配置加载的测试。"""

from __future__ import annotations

import pytest

from core.config import load_settings
from core.errors import ConfigurationError

CONFIG_TEMPLATE = """[llm]
base_url = https://example.invalid/v1
api_key = abc
model = demo-model

[agent]
max_tool_rounds = 4
"""


def test_load_settings_from_file(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text(CONFIG_TEMPLATE, encoding="utf-8")

    settings = load_settings(config)

    assert settings.llm.base_url == "https://example.invalid/v1"
    assert settings.llm.api_key == "abc"
    assert settings.llm.model == "demo-model"
    assert settings.max_tool_rounds == 4
    assert settings.llm.chat_completions_url == "https://example.invalid/v1/chat/completions"


def test_environment_overrides_file(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.ini"
    config.write_text(CONFIG_TEMPLATE, encoding="utf-8")

    monkeypatch.setenv("TAGENT_MODEL", "env-model")
    monkeypatch.setenv("TAGENT_BASE_URL", "https://env.invalid/v1")

    settings = load_settings(config)

    assert settings.llm.model == "env-model"
    assert settings.llm.base_url == "https://env.invalid/v1"


def test_missing_file_raises(tmp_path) -> None:
    with pytest.raises(ConfigurationError):
        load_settings(tmp_path / "not-exists.ini")


def test_missing_section_raises(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text("[other]\nkey = value\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(config)


def test_missing_required_key_raises(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text("[llm]\nbase_url = https://x/v1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(config)


def test_load_search_settings(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text(
        CONFIG_TEMPLATE
        + """
[search]
baidu_qianfan_api_key = qianfan-key
edition = turbo
timeout = 12
top_k = 5
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.search.api_key == "qianfan-key"
    assert settings.search.edition == "turbo"
    assert settings.search.endpoint.endswith("/ai_search/web_search")
    assert settings.search.timeout == 12.0
    assert settings.search.top_k == 5


def test_search_key_accepts_legacy_name(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text(
        CONFIG_TEMPLATE + "\n[search]\nbaidu_qianfan_key = legacy-key\n",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.search.api_key == "legacy-key"
    assert settings.search.edition == "standard"


def test_invalid_search_edition_raises(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text(
        CONFIG_TEMPLATE + "\n[search]\nbaidu_qianfan_api_key = key\nedition = ultimate\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_settings(config)


def test_missing_search_section_is_allowed(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text(CONFIG_TEMPLATE, encoding="utf-8")

    settings = load_settings(config)

    assert settings.search.api_key == ""
    assert settings.search.timeout == 90.0


def test_invalid_search_top_k_raises(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text(
        CONFIG_TEMPLATE + "\n[search]\nbaidu_qianfan_api_key = key\ntop_k = 99\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_settings(config)


def test_with_overrides_keeps_original_immutable(tmp_path) -> None:
    config = tmp_path / "config.ini"
    config.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    settings = load_settings(config)

    updated = settings.with_overrides(llm_model="new-model")

    assert settings.llm.model == "demo-model"
    assert updated.llm.model == "new-model"
