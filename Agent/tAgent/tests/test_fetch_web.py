"""网页正文抓取工具的离线测试（不调用真实 curl / 网络）。"""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from core.tools.builtin import fetch_web
from core.tools.builtin.fetch_web import FetchError, FetchWebTool, build_fetch_tools
from core.tools.registry import ToolRegistry

URL = "https://example.com/article"

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Article</title></head>
<body>
<nav>NAVIGATION MENU</nav>
<main><article>
<h1>Main Heading</h1>
<p>First paragraph with <a href="https://example.com/link">a link</a>.</p>
<h2>Section</h2>
<ul><li>Alpha</li><li>Beta</li></ul>
<table><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>1</td></tr></table>
</article></main>
<footer>FOOTER COPYRIGHT</footer>
</body></html>
"""


def completed(
    args: list[str],
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)


def ok_runner(html: bytes = HTML.encode("utf-8")) -> fetch_web.Runner:
    def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        assert isinstance(args, list)
        assert args[0] == "curl"
        assert "--fail" in args
        assert "--proto" in args
        assert "--proto-redir" in args
        assert URL in args
        assert timeout >= fetch_web.CURL_TIMEOUT
        return completed(args, stdout=html)

    return runner


def make_registry(
    runner: fetch_web.Runner | None = None,
    extractor: fetch_web.Extractor | None = None,
) -> ToolRegistry:
    return ToolRegistry(
        build_fetch_tools(
            curl_path="curl",
            runner=runner or ok_runner(),
            extractor=extractor,
        )
    )


def call(registry: ToolRegistry, **arguments: object):
    return asyncio.run(registry.acall(fetch_web.FETCH_TOOL_NAME, arguments))


def test_fetch_extracts_markdown_and_removes_noise() -> None:
    result = call(make_registry(), url=URL)

    assert result.ok is True
    assert URL in result.output
    assert "正文（Markdown）" in result.output
    assert "# Main Heading" in result.output
    assert "## Section" in result.output
    assert "[a link](https://example.com/link)" in result.output
    assert "- Alpha" in result.output
    assert "| Name | Value |" in result.output
    assert "NAVIGATION MENU" not in result.output
    assert "FOOTER COPYRIGHT" not in result.output


def test_default_runner_uses_argument_list_without_shell(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return completed(args)

    monkeypatch.setattr(fetch_web.subprocess, "run", fake_run)

    fetch_web._default_runner(["curl", URL], 25.0)

    assert captured["args"] == ["curl", URL]
    assert "shell" not in captured["kwargs"]
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["check"] is False


def test_missing_url_returns_clear_error() -> None:
    result = call(make_registry())

    assert result.ok is False
    assert "缺少参数 url" in result.error


def test_invalid_url_returns_clear_error() -> None:
    result = call(make_registry(), url="example.com/article")

    assert result.ok is False
    assert "无效的网页 URL" in result.error


def test_missing_curl_returns_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(fetch_web, "_find_curl", lambda: None)
    registry = ToolRegistry(build_fetch_tools(runner=ok_runner()))

    result = call(registry, url=URL)

    assert result.ok is False
    assert "未找到 curl" in result.error


def test_curl_http_error_is_reported() -> None:
    def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        return completed(
            args,
            returncode=22,
            stderr=b"The requested URL returned error: 404",
        )

    result = call(make_registry(runner=runner), url=URL)

    assert result.ok is False
    assert "服务器返回 HTTP 错误" in result.error
    assert "curl 退出码 22" in result.error
    assert "404" in result.error


def test_curl_timeout_is_reported() -> None:
    def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(args, timeout)

    result = call(make_registry(runner=runner), url=URL)

    assert result.ok is False
    assert "超时" in result.error


def test_empty_response_is_reported() -> None:
    result = call(make_registry(runner=ok_runner(html=b"")), url=URL)

    assert result.ok is False
    assert "内容为空" in result.error


def test_binary_response_is_reported() -> None:
    result = call(make_registry(runner=ok_runner(html=b"\x00\x01\x02")), url=URL)

    assert result.ok is False
    assert "不是 HTML" in result.error


def test_html_parse_error_is_reported() -> None:
    def extractor(html: bytes, url: str) -> str | None:
        raise ValueError("broken html")

    result = call(make_registry(extractor=extractor), url=URL)

    assert result.ok is False
    assert "HTML 解析失败" in result.error
    assert "broken html" in result.error


def test_missing_main_content_is_reported() -> None:
    def extractor(html: bytes, url: str) -> str | None:
        return None

    result = call(make_registry(extractor=extractor), url=URL)

    assert result.ok is False
    assert "正文无法提取" in result.error


def test_long_content_is_truncated() -> None:
    tool = FetchWebTool(
        curl_path="curl",
        runner=ok_runner(html=b"<html>ok</html>"),
        extractor=lambda html, url: "x" * 500,
        max_chars=100,
    )

    output = asyncio.run(tool.fetch(URL))

    assert "已截断" in output
    assert len(output) < 300


def test_fetch_error_type_is_exposed() -> None:
    with pytest.raises(FetchError):
        asyncio.run(FetchWebTool(curl_path="curl", extractor=lambda h, u: "").fetch("bad"))


def test_fallback_text_extract_keeps_content_and_drops_noise() -> None:
    html = (
        "<html><head><title>T</title></head><body>"
        "<script>var secret = 1;</script>"
        "<style>.x{color:red}</style>"
        "<nav>导航菜单 首页 概况</nav>"
        "<footer>版权所有</footer>"
        "<div><p>学校简介：这是一段真实可见的正文内容。</p>"
        '<a href="https://www.neusoft.edu.cn/xxgk">学校概况</a>'
        "</div></body></html>"
    ).encode("utf-8")

    text = fetch_web._fallback_text_extract(html)

    assert text is not None
    assert "学校简介" in text
    assert "真实可见的正文内容" in text
    assert "https://www.neusoft.edu.cn/xxgk" in text
    assert "secret" not in text
    assert "color:red" not in text
    assert "导航菜单" not in text
    assert "版权所有" not in text


def test_fallback_text_extract_returns_none_without_visible_text() -> None:
    html = b"<html><body><script>only js</script><style>a{}</style></body></html>"
    assert fetch_web._fallback_text_extract(html) is None


def test_default_extractor_retries_with_recall(monkeypatch) -> None:
    import trafilatura

    calls: list[bool] = []

    def fake_extract(html, **kwargs):
        calls.append(kwargs.get("favor_recall", False))
        # 精度优先（第一次）返回空，召回优先（第二次）返回正文
        return None if not calls[-1] else "召回模式提取到的正文"

    monkeypatch.setattr(trafilatura, "extract", fake_extract)

    result = fetch_web._default_extractor(b"<html></html>", URL)

    assert result == "召回模式提取到的正文"
    assert calls == [False, True]


def test_default_extractor_falls_back_to_plain_text(monkeypatch) -> None:
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: None)

    html = "<html><body><p>兜底提取的段落文本。</p></body></html>".encode("utf-8")
    result = fetch_web._default_extractor(html, URL)

    assert result is not None
    assert "兜底提取的段落文本" in result
