"""网页正文抓取工具：调用本地 curl 下载 HTML，再用 trafilatura 提取 Markdown。

设计要点：
- 使用参数列表调用 ``curl``，不经过 shell，避免命令注入；
- ``subprocess`` 与正文提取都放到工作线程，避免阻塞前端事件循环；
- 导航栏、广告、页脚等噪声由 trafilatura 过滤，只把正文回传给模型；
- 所有失败都转换成清晰的中文错误，由注册中心回传给模型。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from core.tools.base import ToolSpec

FETCH_TOOL_NAME = "fetchweb"
CURL_TIMEOUT = 20.0
SUBPROCESS_GRACE = 5.0
MAX_DOWNLOAD_BYTES = 5_000_000
MAX_MARKDOWN_CHARS = 20_000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

_CURL_ERRORS = {
    6: "无法解析主机名",
    7: "无法连接到服务器",
    22: "服务器返回 HTTP 错误",
    28: "请求超时",
    35: "TLS/SSL 握手失败",
    63: "网页体积超过限制",
}

Runner = Callable[[list[str], float], subprocess.CompletedProcess[bytes]]
Extractor = Callable[[bytes, str], str | None]


class FetchError(RuntimeError):
    """网页抓取失败；错误信息可直接回传给模型。"""


def _find_curl() -> str | None:
    """定位 curl；Windows 上兼容 PATH 未包含 System32 的情况。"""
    for name in ("curl", "curl.exe"):
        path = shutil.which(name)
        if path:
            return path
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT") or r"C:\Windows"
        candidate = Path(system_root) / "System32" / "curl.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _validate_url(url: str | None) -> str:
    target = (url or "").strip()
    if not target:
        raise FetchError("缺少参数 url：请提供要抓取的网页地址")
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise FetchError(f"无效的网页 URL：{target}（仅支持 http/https 绝对地址）")
    return target


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _default_runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _default_extractor(html: bytes, url: str) -> str | None:
    """提取正文，逐级降级：精度优先 → 召回优先 → 标准库纯文本兜底。

    很多网站首页以导航链接为主，``favor_precision`` 会判定"无正文"；
    换用 ``favor_recall`` 通常能救回简介等文字。若 trafilatura 仍无结果
    （如非标准模板页面），用标准库 :class:`HTMLParser` 做最后一次纯文本提取。
    """
    try:
        import trafilatura
    except ImportError as exc:
        raise FetchError("缺少 trafilatura 依赖，请执行 pip install trafilatura") from exc

    common = dict(
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_links=True,
        include_formatting=True,
        include_images=False,
    )
    extracted = trafilatura.extract(html, favor_precision=True, **common)
    if not (extracted or "").strip():
        extracted = trafilatura.extract(html, favor_recall=True, **common)
    if (extracted or "").strip():
        return extracted.strip()
    return _fallback_text_extract(html)


class _PlainTextExtractor(HTMLParser):
    """trafilatura 全部失败时的兜底解析器：去脚本/导航，只留可见文本与链接。"""

    _SKIP_TAGS = {"script", "style", "noscript", "iframe", "svg", "template"}
    _DROP_TAGS = {"nav", "footer", "header", "aside", "form"}
    _BLOCK_TAGS = {
        "p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "ul", "ol", "section", "article", "blockquote", "dt", "dd", "hr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._drop_depth = 0
        self._chunks: list[str] = []
        self._links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._DROP_TAGS:
            self._drop_depth += 1
        elif tag == "a" and self._skip_depth == 0 and self._drop_depth == 0:
            for key, value in attrs:
                if key == "href" and value:
                    href = value.strip()
                    if href.startswith(("http://", "https://")):
                        self._links.append(href)
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._DROP_TAGS and self._drop_depth:
            self._drop_depth -= 1
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._drop_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        lines: list[str] = []
        previous = ""
        for raw in "".join(self._chunks).splitlines():
            line = " ".join(raw.split())
            if len(line) < 2 or line == previous:
                continue
            lines.append(line)
            previous = line

        links: list[str] = []
        for href in self._links:
            if href not in links:
                links.append(href)
        if links:
            shown = links[:20]
            lines.append("页面链接：" + " | ".join(shown))
        return "\n".join(lines).strip()


def _fallback_text_extract(html: bytes) -> str | None:
    parser = _PlainTextExtractor()
    try:
        parser.feed(_decode(html))
        parser.close()
    except Exception:
        return None
    text = parser.text()
    return text or None


class FetchWebTool:
    """可被 :class:`ToolRegistry` 调用的异步网页正文抓取工具。"""

    def __init__(
        self,
        *,
        curl_path: str | None = None,
        runner: Runner | None = None,
        extractor: Extractor | None = None,
        timeout: float = CURL_TIMEOUT,
        max_chars: int = MAX_MARKDOWN_CHARS,
    ) -> None:
        self._curl_path = curl_path
        self._runner = runner or _default_runner
        self._extractor = extractor or _default_extractor
        self._timeout = timeout
        self._max_chars = max_chars

    async def __call__(self, url: str | None = None, **_: object) -> str:
        return await self.fetch(url)

    async def fetch(self, url: str | None) -> str:
        target = _validate_url(url)
        curl = self._curl_path or _find_curl()
        if not curl:
            raise FetchError(
                "未找到 curl 程序，请先安装 curl 并确保它在 PATH 中（Windows 10+ 通常已内置）"
            )

        args = [
            curl,
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--compressed",
            "--proto",
            "=http,https",
            "--proto-redir",
            "=http,https",
            "--max-redirs",
            "5",
            "--max-time",
            f"{self._timeout:g}",
            "--max-filesize",
            str(MAX_DOWNLOAD_BYTES),
            "--user-agent",
            USER_AGENT,
            target,
        ]

        try:
            completed = await asyncio.to_thread(
                self._runner, args, self._timeout + SUBPROCESS_GRACE
            )
        except subprocess.TimeoutExpired as exc:
            raise FetchError(f"调用 curl 超时（{self._timeout:g} 秒）") from exc
        except FileNotFoundError as exc:
            raise FetchError(f"找不到 curl 程序：{curl}") from exc
        except OSError as exc:
            raise FetchError(f"调用 curl 失败：{exc}") from exc

        if completed.returncode != 0:
            raise FetchError(_curl_error(completed.returncode, completed.stderr))

        html = completed.stdout or b""
        if not html.strip():
            raise FetchError("网页返回内容为空")
        if b"\x00" in html[:4096]:
            raise FetchError("网页返回内容不是 HTML（可能是二进制文件）")

        try:
            markdown = await asyncio.to_thread(self._extractor, html, target)
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(f"HTML 解析失败：{exc}") from exc

        body = (markdown or "").strip()
        if not body:
            raise FetchError(
                "正文无法提取：该页面可能是导航首页、没有可读正文，或内容由 "
                "JavaScript 动态渲染。建议改用 searchweb 搜索该站点的具体页面"
                "（如栏目页或文章页），再把具体 URL 传给 fetchweb；"
                "不要用 RunCli 下载网页"
            )

        if len(body) > self._max_chars:
            body = body[: self._max_chars].rstrip() + "\n\n（正文过长，已截断）"

        return f"网页 URL：{target}\n\n正文（Markdown）：\n{body}"


def _curl_error(returncode: int, stderr: bytes | None) -> str:
    detail = _decode(stderr or b"").strip() or "无错误详情"
    reason = _CURL_ERRORS.get(returncode, "网页访问失败")
    return f"{reason}（curl 退出码 {returncode}）：{detail}"


def build_fetch_tools(
    *,
    curl_path: str | None = None,
    runner: Runner | None = None,
    extractor: Extractor | None = None,
) -> list[ToolSpec]:
    """构造网页正文抓取工具声明。"""
    tool = FetchWebTool(curl_path=curl_path, runner=runner, extractor=extractor)
    return [
        ToolSpec(
            name=FETCH_TOOL_NAME,
            description=(
                "抓取指定网页的正文并转换为 Markdown。当 searchweb 的结果摘要不足，"
                "需要阅读原文、核对细节或提取表格/链接时使用；输入完整的 http/https URL。"
                "工具会自动去除导航栏、广告和页脚。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要抓取的网页完整地址，例如 https://example.com/article",
                    }
                },
                "required": ["url"],
            },
            handler=tool,
        )
    ]


__all__ = [
    "FETCH_TOOL_NAME",
    "FetchError",
    "FetchWebTool",
    "build_fetch_tools",
]
