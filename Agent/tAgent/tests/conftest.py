"""pytest 配置与公共夹具。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import LLMSettings, Settings
from core.session import Session


@pytest.fixture()
def settings() -> Settings:
    """测试用配置（不触碰真实密钥）。"""
    return Settings(
        llm=LLMSettings(
            base_url="https://example.invalid/v1",
            api_key="test-key",
            model="test-model",
            timeout=5.0,
        ),
        max_tool_rounds=3,
        system_prompt="测试用系统提示词",
    )


@pytest.fixture()
def session() -> Session:
    return Session(system_prompt="测试用系统提示词", session_id="test")
