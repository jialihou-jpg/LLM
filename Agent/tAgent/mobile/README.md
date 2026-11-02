# mobile —— 移动端前端（预留）

本目录预留给手机 / 平板端前端。**当前尚未实现**，此处给出实现指引与目录约定，
新增代码时请遵守 [`../docs/FRONTEND_CONTRACT.md`](../docs/FRONTEND_CONTRACT.md)。

## 架构建议

移动端不建议直接跑 Python 核心（体积、耗电、权限都不可控），
推荐沿用"壳 + 服务端"的路线：

```text
┌──────────────┐   HTTP / SSE   ┌──────────────┐   进程内   ┌────────┐
│ 移动端 App    │ ─────────────▶ │ web/ 后端     │ ─────────▶ │ core   │
│ Flutter/React │ ◀───────────── │ (FastAPI)     │            │ 核心   │
│ Native        │                └──────────────┘            └────────┘
└──────────────┘
```

也就是说：`mobile` 目录里放的是**客户端代码**（Flutter / React Native / 原生），
真正的模型调用与工具执行仍在 Python 侧的 `core` 中完成。

## 建议目录结构（Flutter 示例）

```text
mobile/
├── README.md
├── pubspec.yaml
└── lib/
    ├── main.dart
    ├── api/
    │   └── tagent_client.dart    # SSE 客户端
    └── pages/
        └── chat_page.dart
```

## 最小实现要点

移动端只需要一个能消费 SSE 的客户端，并按事件类型更新界面：

| 事件 | 界面动作 |
| --- | --- |
| `AssistantDelta` | 追加到当前气泡末尾 |
| `ToolCallStarted` | 插入一条"正在调用工具"的占位行 |
| `ToolCallCompleted` | 用 `call_id` 找到占位行并回填结果 |
| `ErrorRaised` | 顶部错误提示条 |
| `RunCompleted` | 结束 loading 状态 |

## 注意事项

- 移动端网络不稳定，建议在客户端做**断线重连**与**消息重发**；
- 工具调用会直接作用于服务端文件系统，移动端应默认禁用写操作类工具，
  或在 `build_agent` 时按会话裁剪工具集合；
- 鉴权与多用户隔离在服务端完成（见 `web/README.md`）。

## 启动方式（实现后）

```bash
cd Agent/tAgent/mobile
flutter run
```
