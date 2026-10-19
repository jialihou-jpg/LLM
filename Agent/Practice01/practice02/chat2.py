import configparser
import json
import sys
import time
import subprocess
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("../config.ini", encoding="utf-8") as f:
    config = configparser.ConfigParser()
    config.read_file(f)

base_url = config["llm"]["base_url"].rstrip("/")
api_key = config["llm"]["api_key"]
model = config["llm"]["model"]

# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

def getDate():
    """通过调用本地date命令获取当前日期和时间"""
    try:
        import platform
        system = platform.system()
        if system == "Windows":
            # Windows系统使用cmd命令获取日期和时间
            result_date = subprocess.run(
                ["cmd", "/c", "date", "/t"],
                capture_output=True,
                text=True,
                encoding="gbk",
                errors="replace"
            )
            result_time = subprocess.run(
                ["cmd", "/c", "time", "/t"],
                capture_output=True,
                text=True,
                encoding="gbk",
                errors="replace"
            )
            date_str = result_date.stdout.strip()
            time_str = result_time.stdout.strip()
            return f"当前日期：{date_str}，当前时间：{time_str}"
        else:
            # Linux/macOS系统使用date命令
            result = subprocess.run(
                ["date"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            return result.stdout.strip()
    except Exception as e:
        return f"获取日期时间失败：{str(e)}"

# 工具映射
tool_map = {
    "getDate": getDate
}

messages = [
    {
        "role": "system",
        "content": "你是一个乐于助人的助手。当用户询问日期或时间相关的问题时，请使用getDate工具来获取当前的日期和时间。"
    }
]

while True:
    print("你好，请提出你的问题")
    question = input()
    messages.append({"role": "user", "content": question})

    print("……")
    try:
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
            timeout=60,
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"
        response_data = resp.json()
        
        message = response_data["choices"][0]["message"]
        
        # 检查是否需要调用工具
        if "tool_calls" in message and message["tool_calls"]:
            messages.append(message)
            
            for tool_call in message["tool_calls"]:
                tool_name = tool_call.function.name
                tool_id = tool_call.id
                
                print(f"[调用工具: {tool_name}]")
                
                # 执行工具
                if tool_name in tool_map:
                    tool_func = tool_map[tool_name]
                    tool_result = tool_func()
                    
                    print(f"[工具返回结果: {tool_result}]")
                    
                    # 添加工具结果到消息
                    messages.append({
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "name": tool_name,
                        "content": tool_result
                    })
            
            # 再次请求LLM获取最终回答
            print("……")
            resp2 = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                },
                stream=True,
                timeout=60,
            )
            resp2.raise_for_status()
            resp2.encoding = "utf-8"
            buffer = b""
            done = False
            answer = ""
            for chunk in resp2.iter_content(chunk_size=None):
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
                    content = json.loads(data)["choices"][0]["delta"].get("content")
                    if not content:
                        continue
                    print(content, end="", flush=True)
                    answer += content
                    time.sleep(0.02)
                if done:
                    break
            print()
            messages.append({"role": "assistant", "content": answer})
        else:
            # 不需要调用工具，直接输出回答
            answer = message.get("content", "")
            print(answer)
            messages.append({"role": "assistant", "content": answer})
            
    except Exception as e:
        print(f"请求出错：{e}")
        import traceback
        traceback.print_exc()