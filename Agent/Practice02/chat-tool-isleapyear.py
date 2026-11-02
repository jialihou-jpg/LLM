# -*- coding: utf-8 -*-
import configparser
import json
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
            "name": "isLeapYear",
            "description": "判断输入的年份是否是闰年",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，例如 2024",
                    }
                },
                "required": ["year"],
            },
        },
    }
]


def is_leap_year(year):
    # 用 python 代码计算闰年：能被4整除且不能被100整除，或能被400整除
    year = int(year)
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    return "%d 年%s闰年" % (year, "" if leap else "不是")


def call_tool(name, arguments):
    if name == "isLeapYear":
        try:
            args = json.loads(arguments or "{}")
            return is_leap_year(args["year"])
        except (ValueError, KeyError, TypeError):
            return "isLeapYear 参数错误，应传入 year（整数年份），收到：%s" % arguments
    return "未知的 tool: %s" % name


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
