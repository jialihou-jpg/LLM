import configparser
import json
import sys
import time
import os
import shutil
import mimetypes
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 读取上级目录（Agent/）下的 config.ini，与 Practice01 的约定保持一致
_cfg_paths = [Path(__file__).resolve().parent.parent / "config.ini",
              Path(__file__).resolve().parent / "config.ini"]
_cfg_file = next((p for p in _cfg_paths if p.exists()), _cfg_paths[0])
with open(_cfg_file, encoding="utf-8") as f:
    config = configparser.ConfigParser()
    config.read_file(f)

base_url = config["llm"]["base_url"].rstrip("/")
api_key = config["llm"]["api_key"]
model = config["llm"]["model"]

# 纯文本文件后缀白名单（仅这些后缀允许读取/编辑内容）
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".pyw", ".ini", ".cfg", ".toml", ".yaml", ".yml",
    ".json", ".jsonl", ".csv", ".tsv", ".xml", ".html", ".htm", ".css", ".js", ".mjs",
    ".ts", ".jsx", ".tsx", ".sh", ".bash", ".bat", ".cmd", ".ps1", ".c", ".h", ".cpp",
    ".hpp", ".cc", ".java", ".go", ".rs", ".sql", ".log", ".env", ".gitignore", ".mmd",
}


# ----------------------------- 本地文件操作工具实现 -----------------------------

def tool_getcwd():
    """1. 获取当前工作目录"""
    return f"当前工作目录：{os.getcwd()}"


def tool_list_dir(path="."):
    """2. 列出指定目录下所有文件和子目录"""
    p = Path(path).expanduser()
    if not p.exists():
        return f"目录不存在：{path}"
    if not p.is_dir():
        return f"不是目录：{path}"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines = [f"目录：{p.resolve()}（共 {len(items)} 项）"]
    for child in items:
        tag = "目录" if child.is_dir() else "文件"
        size = "" if child.is_dir() else f"  {child.stat().st_size}B"
        lines.append(f"  [{tag}] {child.name}{size}")
    return "\n".join(lines)


def tool_get_file_type(path):
    """3. 获取指定文件的文件类型"""
    p = Path(path).expanduser()
    if not p.exists():
        return f"路径不存在：{path}"
    if p.is_dir():
        return f"{p.resolve()}\n类型：目录（文件夹）"
    mime, _ = mimetypes.guess_type(str(p))
    ext = p.suffix.lower() or "无"
    size = p.stat().st_size
    return (f"路径：{p.resolve()}\n"
            f"类型：普通文件\n"
            f"扩展名：{ext}\n"
            f"MIME：{mime or '未知'}\n"
            f"大小：{size} 字节")


def _is_text_file(p: Path) -> bool:
    """通过后缀白名单 + 二进制嗅探判断是否为纯文本文件"""
    if p.suffix.lower() in TEXT_EXTENSIONS:
        return True
    try:
        with open(p, "rb") as f:
            chunk = f.read(4096)
    except Exception:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def tool_read_file(path):
    """4. 获取指定文件的内容（仅支持纯文本格式文件）"""
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return f"文件不存在：{path}"
    if not _is_text_file(p):
        return f"拒绝读取：{path} 是二进制文件，仅支持纯文本格式。"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"读取失败：{e}"
    return f"文件：{p.resolve()}\n字符数：{len(content)}\n---- 文件内容开始 ----\n{content}\n---- 文件内容结束 ----"


def tool_create_file(dir_path, filename):
    """5. 根据指定的目录和文件名创建新文件"""
    d = Path(dir_path).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
    if f.exists():
        return f"创建失败：文件已存在 -> {f.resolve()}（如需写入内容请使用 edit_file）"
    f.touch()
    return f"已创建空文件：{f.resolve()}"


def tool_edit_file(path, content):
    """6. 编辑指定文件的内容（仅支持纯文本格式文件，整体覆盖写入）"""
    p = Path(path).expanduser()
    if not p.exists():
        return f"编辑失败：文件不存在 -> {path}（请先使用 create_file 创建）"
    if p.is_dir():
        return f"编辑失败：{path} 是目录，不是文件"
    if not _is_text_file(p):
        return f"拒绝编辑：{path} 是二进制文件，仅支持纯文本格式。"
    p.write_text(content, encoding="utf-8")
    return f"已写入 {len(content)} 个字符到：{p.resolve()}"


def tool_make_dir(path):
    """7. 创建新目录（含父目录）"""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return f"目录就绪：{p.resolve()}"


def tool_remove_dir(path):
    """8. 删除目录（非空，递归删除目录及其全部内容）"""
    p = Path(path).expanduser()
    if not p.exists():
        return f"删除失败：目录不存在 -> {path}"
    if not p.is_dir():
        return f"删除失败：{path} 不是目录"
    shutil.rmtree(p)
    return f"已递归删除目录及其全部内容：{p.resolve()}"


def tool_remove_file(path):
    """9. 删除文件"""
    p = Path(path).expanduser()
    if not p.exists():
        return f"删除失败：文件不存在 -> {path}"
    if p.is_dir():
        return f"删除失败：{path} 是目录，请使用 remove_dir"
    p.unlink()
    return f"已删除文件：{p.resolve()}"


def tool_rename_path(old_path, new_path):
    """10. 重命名文件和目录"""
    old = Path(old_path).expanduser()
    if not old.exists():
        return f"重命名失败：原路径不存在 -> {old_path}"
    new = Path(new_path).expanduser()
    old.rename(new)
    return f"已重命名：{old.resolve()} -> {new.resolve()}"


# ----------------------------- OpenAI function-calling 声明 -----------------------------

def _props(**kw):
    return kw


tools = [
    {"type": "function", "function": {
        "name": "getcwd",
        "description": "获取当前工作目录的绝对路径。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "列出指定目录下所有文件和子目录。path 缺省为当前目录。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "目标目录路径，默认当前目录"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_file_type",
        "description": "获取指定路径的类型信息：目录还是文件、扩展名、MIME 类型、大小。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "目标文件或目录路径"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取纯文本文件内容。二进制文件（图片、视频、压缩包等）会被拒绝。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "待读取的纯文本文件路径"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "create_file",
        "description": "在指定目录下创建一个空的新文件；目录不存在会自动创建。",
        "parameters": {"type": "object", "properties": {
            "dir_path": {"type": "string", "description": "所在目录路径"},
            "filename": {"type": "string", "description": "新文件名（含扩展名）"},
        }, "required": ["dir_path", "filename"]},
    }},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "整体覆盖写入纯文本文件内容（仅支持纯文本文件）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "目标文件路径"},
            "content": {"type": "string", "description": "要写入的完整文本内容"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "make_dir",
        "description": "创建新目录，父目录不存在时一并创建。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "要创建的目录路径"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "remove_dir",
        "description": "递归删除一个非空目录及其全部内容（危险操作，不可恢复）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "要删除的目录路径"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "remove_file",
        "description": "删除一个文件（不可恢复）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "要删除的文件路径"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "rename_path",
        "description": "重命名或移动文件/目录到新路径。",
        "parameters": {"type": "object", "properties": {
            "old_path": {"type": "string", "description": "原路径"},
            "new_path": {"type": "string", "description": "新路径"},
        }, "required": ["old_path", "new_path"]},
    }},
]

tool_map = {
    "getcwd": tool_getcwd,
    "list_dir": tool_list_dir,
    "get_file_type": tool_get_file_type,
    "read_file": tool_read_file,
    "create_file": tool_create_file,
    "edit_file": tool_edit_file,
    "make_dir": tool_make_dir,
    "remove_dir": tool_remove_dir,
    "remove_file": tool_remove_file,
    "rename_path": tool_rename_path,
}

messages = [
    {
        "role": "system",
        "content": (
            "你是一个可以操作本地文件系统的助手。用户询问目录、文件内容、创建/删除/重命名等问题时，"
            "必须调用对应的 function 工具完成真实操作，不要凭空编造路径或内容。"
            "危险操作（remove_dir / remove_file）执行前要在回答中说明将删除什么。"
        ),
    }
]


# ----------------------------- 流式输出辅助 -----------------------------

def stream_chat(msgs):
    """发起流式请求并逐字打印，返回完整回答文本。"""
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": msgs, "stream": True},
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    buffer = b""
    answer = ""
    done = False
    for chunk in resp.iter_content(chunk_size=None):
        if not chunk:
            continue
        buffer += chunk
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            line = raw.rstrip(b"\r").decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data == "[DONE]":
                done = True
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content")
            except Exception:
                continue
            if not delta:
                continue
            print(delta, end="", flush=True)
            answer += delta
            time.sleep(0.02)
        if done:
            break
    print()
    return answer


# ----------------------------- 主循环 -----------------------------

def main():
    print("你好，请提出与本地文件/目录操作相关的问题（输入 exit 退出）")
    while True:
        try:
            question = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not question.strip():
            continue
        if question.strip().lower() in {"exit", "quit"}:
            print("再见。")
            break
        messages.append({"role": "user", "content": question})

        print("……", flush=True)
        try:
            # 首轮：非流式，便于判断 tool_calls
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            message = resp.json()["choices"][0]["message"]

            if message.get("tool_calls"):
                messages.append(message)
                for call in message["tool_calls"]:
                    name = call["function"]["name"]
                    tool_id = call["id"]
                    try:
                        args = json.loads(call["function"].arguments or "{}")
                    except Exception:
                        args = {}
                    print(f"[调用工具: {name}({args})]", flush=True)
                    func = tool_map.get(name)
                    if func is None:
                        result = f"未知工具：{name}"
                    else:
                        try:
                            result = func(**args)
                        except TypeError as e:
                            result = f"参数错误：{e}；收到参数：{args}"
                        except Exception as e:
                            result = f"工具执行失败：{e}"
                    print(f"[工具返回] {result}", flush=True)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": name,
                        "content": result,
                    })

                print("……", flush=True)
                answer = stream_chat(messages)
                messages.append({"role": "assistant", "content": answer})
            else:
                answer = message.get("content", "")
                print(answer)
                messages.append({"role": "assistant", "content": answer})
        except Exception as e:
            print(f"请求出错：{e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
