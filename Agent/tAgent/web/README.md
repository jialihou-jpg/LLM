# web —— Web 前端（预留）

本目录预留给基于浏览器的 Web 前端。**当前尚未实现**，此处给出实现指引与目录约定，
新增代码时请遵守 [`../docs/FRONTEND_CONTRACT.md`](../docs/FRONTEND_CONTRACT.md)。

## 建议技术栈

| 组件 | 选型 | 说明 |
| --- | --- | --- |
| 后端 | FastAPI + Uvicorn | 提供会话接口与 SSE 流式推送 |
| 前端 | 原生 JS / Vue / React | 任意，只需能消费 SSE |
| 协议 | HTTP + SSE | 与 TUI 共用同一套核心事件 |

## 建议目录结构

```text
web/
├── __init__.py
├── __main__.py        # uvicorn 入口：python -m web
├── app.py             # FastAPI 应用、路由、会话管理
├── schemas.py         # 请求 / 响应模型（pydantic）
├── static/            # 前端静态资源
│   ├── index.html
│   └── app.js
└── requirements.txt   # fastapi / uvicorn
```

## 最小实现要点

```python
# web/app.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from core.config import load_settings
from core.factory import build_agent

app = FastAPI()
settings = load_settings()
agents: dict[str, object] = {}


def get_agent(session_id: str):
    if session_id not in agents:
        agents[session_id] = build_agent(settings)
    return agents[session_id]


@app.post("/api/chat")
async def chat(session_id: str, question: str) -> StreamingResponse:
    agent = get_agent(session_id)

    async def event_source():
        async for event in agent.run(question):
            yield f"data: {event_to_dict(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
```

事件到 JSON 的映射规则见前端契约文档第 3 节；由于 `core.events` 中全部是
dataclass，可直接用 `dataclasses.asdict()` 序列化。

## 与 TUI 的差异

- TUI 是**单用户、单进程**；Web 需要**多会话**（`session_id → Agent` 映射）。
- TUI 直接消费异步生成器；Web 需要把事件转成 SSE 或 WebSocket 帧。
- Web 前端不能直接访问本地文件系统工具的运行目录，需要在服务端限定工作目录。

## 启动方式（实现后）

```powershell
cd Agent/tAgent
pip install -e ".[web]"
python -m web --host 127.0.0.1 --port 8000
```
