# desktop —— 桌面端前端（预留）

本目录预留给桌面应用前端。**当前尚未实现**，此处给出实现指引与目录约定，
新增代码时请遵守 [`../docs/FRONTEND_CONTRACT.md`](../docs/FRONTEND_CONTRACT.md)。

## 两种可选路线

| 路线 | 说明 | 适用场景 |
| --- | --- | --- |
| A. 壳 + Web | 用 Tauri / Electron 包装 `web/` 的页面，核心逻辑仍在 Python 侧 | 快速交付、复用 Web 实现 |
| B. 原生 GUI | 用 PySide6 / tkinter / Avalonia 直接消费 `core` 事件流 | 需要深度集成系统能力 |

路线 A 只需在 `web/` 完成后增加壳工程；路线 B 与 TUI 类似，
直接 `async for event in agent.run(question)` 即可。

## 建议目录结构（路线 B）

```text
desktop/
├── __init__.py
├── __main__.py        # 入口：python -m desktop
├── app.py             # 窗口与事件绑定
├── widgets/           # 与 tui/widgets 同构的组件
└── requirements.txt
```

## 最小实现要点

```python
# desktop/app.py
import asyncio

from core.factory import build_agent


class DesktopApp:
    def __init__(self) -> None:
        self.agent = build_agent()

    async def send(self, question: str) -> None:
        async for event in self.agent.run(question):
            if event.__class__.__name__ == "AssistantDelta":
                self.append_to_view(event.text)
```

要点：

- GUI 框架的线程模型通常不是 asyncio，调用 `agent.run()` 时需要把事件
  通过 `asyncio.run_coroutine_threadsafe` 或信号/槽机制投递回 UI 线程；
- TUI 已经验证过的事件消费方式（节流刷新、按 `call_id` 配对工具调用）可直接照搬。

## 与 TUI 的差异

| 维度 | TUI | Desktop |
| --- | --- | --- |
| 渲染 | 终端字符 | GUI 控件 |
| 流式刷新 | `Static.update` + 节流 | `QTextEdit.append` / `insertPlainText` |
| 布局 | Textual CSS | 布局管理器 |
| 事件循环 | Textual 自带 | 需自行桥接 |

## 启动方式（实现后）

```powershell
cd Agent/tAgent
pip install -e ".[desktop]"   # 依赖在实现时确定
python -m desktop
```
