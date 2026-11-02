# 前端接入契约（Frontend Contract）

本文件是 `core` 与各个前端（`tui` / `web` / `desktop` / `mobile`）之间的唯一约定。
新增前端时只需遵守本契约，**不需要修改 `core` 中任何代码**。

## 1. 依赖方向

```text
        ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
        │   tui    │   │   web    │   │ desktop  │   │  mobile  │
        └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘
             │              │              │              │
             └──────────────┴──────┬───────┴──────────────┘
                                   │  只依赖 core
                            ┌──────▼──────┐
                            │    core     │  模型调用 / 工具执行 / 会话状态
                            └──────┬──────┘
                                   │
                         ┌─────────▼─────────┐
                         │  OpenAI 兼容服务   │
                         └───────────────────┘
```

硬性约束：

1. `core` **不得**导入 `tui` / `web` / `desktop` / `mobile` 中的任何模块；
2. `core` **不得**依赖 Textual / FastAPI / Qt 等界面框架；
3. 前端之间**不得**互相导入；
4. 前端只允许通过 `core.factory.build_agent` 获取 Agent 实例。

## 2. 组装 Agent

```python
from core.config import load_settings
from core.factory import build_agent

settings = load_settings()          # 自动查找 config.ini，也支持环境变量覆盖
agent = build_agent(settings)       # 组合 LLM 客户端 + 工具注册中心 + 会话
```

自定义工具：

```python
from core.tools.base import ToolSpec

agent.register_tools([
    ToolSpec(
        name="upper",
        description="把文本转成大写",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        handler=lambda **kw: kw["text"].upper(),
    )
])
```

## 3. 事件流 API

`Agent.run()` 是一个**异步生成器**，按顺序产出 `core.events` 中的事件：

| 事件 | 字段 | 含义 |
| --- | --- | --- |
| `RunStarted` | `user_input` | 本轮开始 |
| `AssistantDelta` | `text` | 回答增量（流式，可直接拼接） |
| `AssistantCompleted` | `text` | **一个模型轮次**的回答结束（每轮都会触发一次） |
| `ToolCallStarted` | `call_id`, `name`, `arguments` | 即将执行工具 |
| `ToolCallCompleted` | `call_id`, `name`, `result`, `ok` | 工具执行结束 |
| `ErrorRaised` | `message`, `detail` | 出错（网络、模型、配置） |
| `RunCompleted` | `rounds`, `success` | 本轮（一次提问）结束 |

使用方式（以 Web 的 SSE 为例）：

```python
async for event in agent.run(question):
    if isinstance(event, AssistantDelta):
        yield f"data: {json.dumps({'type': 'delta', 'text': event.text})}\n\n"
    elif isinstance(event, ToolCallStarted):
        yield f"data: {json.dumps({'type': 'tool_start', 'name': event.name})}\n\n"
    ...
```

要点：

- **事件顺序即真实执行顺序**，前端按到达顺序渲染即可；
- `ToolCallStarted` 一定早于同 `call_id` 的 `ToolCallCompleted`；
- 一个模型轮次 = 一段 `AssistantDelta` + 一个 `AssistantCompleted`；
  一次 `run()` 可能包含多个轮次（"模型 → 工具 → 模型"），`RunCompleted` 是最后一个事件；
- `AssistantCompleted.text` 是该轮**清洗后**的最终文本（已去掉服务商混入的模板碎片），
  前端应以它覆盖流式拼接结果；
- 工具调用在进入事件流前已被**归一化**：`name` 一定是真实工具名，`arguments` 一定是
  可解析的 JSON 对象（服务商把整段调用塞进参数、缺调用 id 等情况都已修正），
  前端可以直接展示 `ToolCallStarted.arguments`；
- 建议前端**每个模型轮次一个气泡**：收到 `AssistantCompleted` 后关闭当前气泡，
  下一轮再开新气泡。

## 4. 会话状态

- `agent.session` 保存完整消息历史，`agent.history` 可读取消息列表；
- `agent.reset()` 清空历史但保留 system prompt（换话题时调用）；
- **一个 Agent 实例对应一个会话**。多用户场景请为每个用户创建独立实例：

```python
sessions: dict[str, Session] = {}

def get_agent(user_id: str) -> Agent:
    if user_id not in sessions:
        session = Session(system_prompt=settings.system_prompt, session_id=user_id)
        sessions[user_id] = session
        agent = build_agent(settings, session=session)
    return sessions[user_id]
```

## 5. 错误处理

| 场景 | 表现 | 前端处理建议 |
| --- | --- | --- |
| 配置缺失 | `on_mount` 时 `ConfigurationError` | 提示用户复制 `config.example.ini` |
| 网络 / 模型报错 | `ErrorRaised` 事件 | 展示错误文案，允许重试 |
| 工具参数非法 | `ToolCallCompleted(ok=False)` | 展示原始错误，模型会自动重试 |
| 超过最大轮次 | `ErrorRaised` + `RunCompleted(success=False)` | 提示用户重述问题 |

## 6. 生命周期

```python
try:
    ...
finally:
    await agent.aclose()   # 释放底层 HTTP 连接
```

前端退出（Web 进程重启、Desktop 窗口关闭、TUI 退出）时应调用 `aclose()`。

## 7. 扩展点

| 需求 | 做法 |
| --- | --- |
| 更换模型服务商 | 实现 `core.llm.client.LLMClient` 协议，注入 `build_agent(client=...)` |
| 新增工具 | 写 `ToolSpec` 并 `register_tools` / `build_agent(extra_tools=[...])` |
| 修改系统提示词 | `config.ini` 的 `[agent] system_prompt`，或构造 `Session(system_prompt=...)` |
| 自定义流式节奏 | 前端自行节流（`tui` 中为 60ms 一次） |
