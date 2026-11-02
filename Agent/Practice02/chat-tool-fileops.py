# -*- coding: utf-8 -*-
import configparser
import json
import mimetypes
import os
import sys
import warnings

# 屏蔽 requests 对 chardet/urllib3 的版本误报（环境里 reportlab 装的 chardet 版本超范围，不影响功能）
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 读取与本文件同目录下的 config.ini
cfg = configparser.ConfigParser()
cfg.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini"), encoding="utf-8")
base_url = cfg["llm"]["base_url"].strip().rstrip("/")
api_key = cfg["llm"]["api_key"].strip()
model = cfg["llm"]["model"].strip()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getcwd",
            "description": "获取当前工作目录",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDir",
            "description": "列出指定目录下所有文件和子目录，不传 path 时列出当前工作目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要列出的目录路径"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定文件的文件类型（MIME 类型、扩展名、是否纯文本）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "获取指定文件的内容，仅支持纯文本格式文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "根据指定的目录和文件名创建新文件，可选写入初始内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "文件所在目录路径"},
                    "filename": {"type": "string", "description": "文件名，含扩展名"},
                    "content": {"type": "string", "description": "写入文件的初始内容，默认为空"},
                },
                "required": ["directory", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editFile",
            "description": "编辑指定文件的内容（把文件中的 old_text 替换为 new_text），仅支持纯文本格式文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_text": {"type": "string", "description": "要被替换的原文本"},
                    "new_text": {"type": "string", "description": "替换后的新文本"},
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有匹配项，默认只替换第一处",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
]


def _decode(raw):
    for enc in ("utf-8", "gbk", sys.getfilesystemencoding()):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw:
        return None, "文件不是纯文本格式（含二进制内容）：%s" % path
    return _decode(raw), None


def get_cwd():
    return os.getcwd()


def list_dir(path="."):
    path = path or "."
    if not os.path.isdir(path):
        return "目录不存在：%s" % path
    entries = []
    with os.scandir(path) as it:
        for e in sorted(it, key=lambda x: (not x.is_dir(), x.name.lower())):
            entries.append(("[DIR]  " if e.is_dir() else "[FILE] ") + e.name)
    header = "目录 %s，共 %d 项" % (os.path.abspath(path), len(entries))
    if not entries:
        return header + "（空目录）"
    return header + "：\n" + "\n".join(entries)


def get_file_type(path):
    if not os.path.isfile(path):
        return "文件不存在：%s" % path
    ext = os.path.splitext(path)[1]
    mime, _ = mimetypes.guess_type(path)
    text, err = _read_text(path)
    return "文件 %s\n扩展名：%s\nMIME 类型：%s\n是否纯文本：%s" % (
        os.path.abspath(path),
        ext or "（无）",
        mime or "application/octet-stream",
        "是" if err is None else "否",
    )


def read_file(path):
    if not os.path.isfile(path):
        return "文件不存在：%s" % path
    text, err = _read_text(path)
    if err:
        return err
    size = os.path.getsize(path)
    limit = 50000
    if len(text) > limit:
        return "文件 %s（%d 字节）内容过长，仅返回前 %d 字符：\n%s" % (path, size, limit, text[:limit])
    return "文件 %s（%d 字节）内容：\n%s" % (path, size, text)


def create_file(directory, filename, content=""):
    if not directory:
        return "directory 不能为空"
    if not filename:
        return "filename 不能为空"
    if os.path.sep in filename or (os.path.altsep and os.path.altsep in filename):
        return "filename 中不能包含路径分隔符，请把目录写在 directory 参数中"
    if os.path.isdir(directory) and os.path.exists(os.path.join(directory, filename)):
        return "文件已存在，未覆盖：%s" % os.path.join(directory, filename)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    data = content or ""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
    return "已创建文件 %s（%d 字符）" % (os.path.abspath(path), len(data))


def edit_file(path, old_text, new_text, replace_all=False):
    if not os.path.isfile(path):
        return "文件不存在：%s" % path
    text, err = _read_text(path)
    if err:
        return err
    if old_text == "":
        return "old_text 不能为空；如需覆盖整个文件内容请先说明"
    count = text.count(old_text)
    if count == 0:
        return "在文件 %s 中未找到 old_text" % path
    if not replace_all:
        count = 1
        new_text_final = text.replace(old_text, new_text, 1)
    else:
        new_text_final = text.replace(old_text, new_text)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text_final)
    return "已编辑文件 %s，替换 %d 处" % (os.path.abspath(path), count)


def call_tool(name, arguments):
    try:
        args = json.loads(arguments or "{}")
    except ValueError:
        return "%s 参数不是合法 JSON：%s" % (name, arguments)
    try:
        if name == "getcwd":
            return get_cwd()
        if name == "listDir":
            return list_dir(args.get("path") or ".")
        if name == "getFileType":
            return get_file_type(args["path"])
        if name == "readFile":
            return read_file(args["path"])
        if name == "createFile":
            return create_file(args.get("directory", ""), args.get("filename", ""), args.get("content", ""))
        if name == "editFile":
            return edit_file(
                args["path"],
                args["old_text"],
                args["new_text"],
                bool(args.get("replace_all", False)),
            )
    except (KeyError, TypeError) as e:
        return "%s 参数缺失或类型错误：%s（收到：%s）" % (name, e, arguments)
    except OSError as e:
        return "文件操作失败：%s" % e
    return "未知的 tool：%s" % name


def stream_chat(messages):
    resp = requests.post(
        base_url + "/chat/completions",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "stream": True, "tools": TOOLS},
        stream=True,
        timeout=60,
    )
    if resp.status_code != 200:
        print("HTTP %s: %s" % (resp.status_code, resp.text[:300]))
        sys.exit(1)
    # SSE 响应头不带 charset，requests 会按 ISO-8859-1 解码，这里强制用 UTF-8，否则中文乱码
    resp.encoding = "utf-8"
    reply = []
    tool_calls = {}
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            delta = json.loads(data)["choices"][0].get("delta") or {}
        except (ValueError, KeyError, IndexError):
            continue
        content = delta.get("content")
        if content:
            print(content, end="", flush=True)
            reply.append(content)
        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0)
            slot = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            if tc.get("id"):
                slot["id"] = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["name"] = fn["name"]
            if fn.get("arguments"):
                slot["arguments"] += fn["arguments"]
    print()
    calls = [tool_calls[i] for i in sorted(tool_calls)]
    for i, c in enumerate(calls):
        if not c["id"]:
            c["id"] = "call_%d" % i
    return "".join(reply), calls


def main():
    history = []  # 存已完成的问答，每一轮都把全部历史一起发给模型

    while True:
        try:
            prompt = input("please input your prompt: ")
        except EOFError:
            print()
            break
        print("---")
        messages = history + [{"role": "user", "content": prompt}]

        while True:
            try:
                content, calls = stream_chat(messages)
            except requests.RequestException as e:
                print("请求失败：%s" % e)
                sys.exit(1)

            if not calls:
                history.append({"role": "user", "content": prompt})
                history.append({"role": "assistant", "content": content})
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"] or "{}"},
                        }
                        for c in calls
                    ],
                }
            )
            for c in calls:
                result = call_tool(c["name"], c["arguments"])
                print("[tool %s] %s" % (c["name"], result))
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
