# Practice02 — 流式对话 + 本地文件操作 Function 工具

在 [Practice01](../Practice01/) 最小流式对话的基础上，给 LLM 接上一组
**本地文件系统操作工具**，演示完整的 function-calling 闭环：

> 用户自然语言 → LLM 决定调用哪个工具 → 本地执行 → 结果回灌 → LLM 流式总结回答。

## 文件清单

| 文件 | 说明 |
| --- | --- |
| `chat-stream-tool-getDate.py` | 循环流式对话 + `getDate` 工具，通过 subprocess 调用本地 `date` 命令获取日期时间 |
| `chat-stream-tool-fileOps.py` | 主程序：OpenAI 兼容流式对话 + 10 个文件操作 function |
| `chat-stream-tool-fileOps.mmd` | 本程序的代码架构图（Mermaid 源码，GitHub / VS Code 可直接渲染） |
| `README.md` | 本文档 |

## getDate 小工具演示

```powershell
python chat-stream-tool-getDate.py
> 今天几号了？
```

LLM 会自动调用 `getDate` 工具（底层是 `subprocess` 调用系统 `date` 命令，Windows 走 `cmd /c date /t` + `time /t`，Linux/macOS 走 `date`），再把结果流式念给你听。

## 内置的 10 个本地文件工具

| # | 函数名 | 作用 |
| --- | --- | --- |
| 1 | `getcwd` | 获取当前工作目录 |
| 2 | `list_dir` | 列出指定目录下所有文件和子目录 |
| 3 | `get_file_type` | 获取指定文件的扩展名 / MIME / 大小 |
| 4 | `read_file` | 读取纯文本文件内容（二进制文件拒绝读取） |
| 5 | `create_file` | 根据目录和文件名创建空新文件 |
| 6 | `edit_file` | 整体覆盖写入纯文本文件内容 |
| 7 | `make_dir` | 创建新目录（含父目录） |
| 8 | `remove_dir` | 递归删除非空目录（危险操作） |
| 9 | `remove_file` | 删除文件 |
| 10 | `rename_path` | 重命名 / 移动文件和目录 |

实现方式：直接使用 Python 标准库 `os` / `pathlib` / `shutil` / `mimetypes`，
不依赖任何第三方 CLI 命令，跨平台一致。

## 运行方式

### 1. 准备配置文件

在 `Agent/` 目录（即本目录的上一级）放置 `config.ini`（已被 `.gitignore` 忽略，
不会上传）：

```ini
[llm]
base_url = https://api.siliconflow.cn/v1
api_key = 你的 API Key
model = Qwen/Qwen3-8B
```

程序会按以下顺序寻找配置：

1. `Agent/config.ini`（推荐）
2. `Agent/Practice02/config.ini`

### 2. 安装依赖并启动

```powershell
cd E:\LLM\Agent\Practice02
pip install requests
python chat-stream-tool-fileOps.py
```

### 3. 试试这些提问

```
> 我现在在哪个目录？
> 帮我看看 E:\LLM\Agent 下面都有什么
> 在当前目录建一个 notes 文件夹，里面新建一个 todo.txt，写入"买牛奶"
> 读一下 todo.txt 的内容
> 把 todo.txt 改名为 shopping.txt
> 删除刚才建的 notes 文件夹
```

输入 `exit` 或按 `Ctrl+C` 退出。

## 工作流程（对应架构图）

```
用户输入
   │
   ▼
POST /chat/completions  (stream=false, 带 tools 声明)
   │
   ├── LLM 直接回答 ──────────────► 打印回答，进入下一轮
   │
   └── LLM 返回 tool_calls
           │
           ▼
   按 name 在 tool_map 中分发，调用对应 Python 函数
           │
           ▼
   工具结果作为 role=tool 消息回灌 messages
           │
           ▼
POST /chat/completions  (stream=true, 不带 tools)
           │
           ▼
   SSE 逐字打印 LLM 的总结回答
```

完整可视化见 [`chat-stream-tool-fileOps.mmd`](./chat-stream-tool-fileOps.mmd)，
在 GitHub 仓库页面或 VS Code 安装 Mermaid 插件后即可渲染。

## 安全说明

- `read_file` / `edit_file` 在写入或读取前会做**纯文本判定**：
  先查后缀白名单（`.py .md .json .txt .csv .html .css .js ...`），
  再嗅探前 4KB 是否含 `\x00` 字节，命中二进制则直接拒绝。
- `remove_dir` / `remove_file` 是**不可逆**操作，system 提示词已要求
  LLM 在执行前向用户说明将删除什么。
- 工具运行在你本机当前工作目录下，拥有该进程同等的文件系统权限，
  请勿在生产环境或敏感目录下运行。
