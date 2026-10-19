import configparser
import json
import sys
import time
import subprocess
import platform
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 读取上级目录（Agent/）下的 config.ini
_cfg_paths = [Path(__file__).resolve().parent.parent / "config.ini",
              Path(__file__).resolve().parent / "config.ini"]
_cfg_file = next((p for p in _cfg_paths if p.exists()), _cfg_paths[0])
with open(_cfg_file, encoding="utf-8") as f:
    config = configparser.ConfigParser()
    config.read_file(f)

base_url = config["llm"]["base_url"].rstrip("/")
api_key = config["llm"]["api_key"]
model = config["llm"]["model"]


# ----------------------------- 工具实现：调用本地 date 命令 -----------------------------

def getDate():
    """通过调用本地系统的 date 命令获取当前电脑的日期和时间。

    注意：不使用 Python 的 datetime 模块，而是用 subprocess 起一个本地进程
    执行系统自带的 date 命令，跨平台兼容。
    """
    try:
        system = platform.system()
        if system == "Windows":
            # Windows：分别调用 date /t 和 time /t
            r_date = subprocess.run(
                ["cmd", "/c", "date", "/t"],
                capture_output=True, text=True,
                encoding="gbk", errors="replace",
            )
            r_time = subprocess.run(
                ["cmd", "/c", "time", "/t"],
                capture_output=True, text=True,
                encoding="gbk", errors="replace",
            )
            date_str = r_date.stdout.strip()
            time_str = r_time.stdout.strip()
            return f"当前日期：{date_str}，当前时间：{time_str}"
        else:
            # Linux / macOS：直接调用 date 命令
            r = subprocess.run(
                ["date"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            return r.stdout.strip()
    except Exception as e:
        return f"调用 date 命令失败：{e}"


# ----------------------------- OpenAI function-calling 声明 -----------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的本地日期和时间。底层通过调用操作系统自带的 date 命令实现。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }
]

tool_map = {
    "getDate": getDate,
}


# ----------------------------- 流式输出辅助 -----------------------------

def stream_chat(msgs):
    """发起流式请求并逐字打印，返回完整回答文本。"""
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": msgs, "stream": True},
        stream=True, timeout=120,
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


# ----------------------------- 主循环：保留多轮历史 -----------------------------

messages = [
    {
        "role": "system",
        "content": "你是一个乐于助人的助手。当用户询问日期或时间相关问题时，请调用 getDate 工具获取当前电脑的日期时间。",
    }
]


def main():
    print("你好，请提出你的问题（输入 exit 退出）")
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

        # 用户消息追加进历史
        messages.append({"role": "user", "content": question})

        print("……", flush=True)
        try:
            # 首轮：非流式，便于判断是否需要调用工具
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
                # LLM 要求调用工具
                messages.append(message)
                for call in message["tool_calls"]:
                    name = call["function"]["name"]
                    tool_id = call["id"]
                    print(f"[调用工具: {name}]", flush=True)
                    result = tool_map[name]()
                    print(f"[工具返回] {result}", flush=True)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": name,
                        "content": result,
                    })

                # 二轮流式输出总结
                print("……", flush=True)
                answer = stream_chat(messages)
                messages.append({"role": "assistant", "content": answer})
            else:
                # 直接回答
                answer = message.get("content", "")
                print(answer)
                messages.append({"role": "assistant", "content": answer})

        except Exception as e:
            print(f"请求出错：{e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
