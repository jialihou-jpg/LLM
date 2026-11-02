# tAgent

在 [`Agent/Practice02/file_chat.py`](../Practice02/file_chat.py) 基础上重构的智能体项目：
把**核心业务逻辑**与**界面代码**彻底分离，先落地 Textual 终端界面（TUI），
并为后续的 Web / Desktop / Mobile 界面预留了统一的接入契约。

```text
core/    ← 纯业务：配置、会话、模型调用、工具执行、编排（不依赖任何界面框架）
tui/     ← Textual 终端界面：只消费 core 的事件流
web/     ← 预留：Web 前端
desktop/ ← 预留：桌面端前端
mobile/  ← 预留：移动端前端
docs/    ← 前端接入契约
tests/   ← core 与 tui 的自动化测试
```

## 特性

- **分层清晰**：`core` 不导入任何界面库，前端之间也互不依赖；
- **事件驱动**：`Agent.run()` 以异步生成器产出事件，TUI / Web / SSE 复用同一套逻辑；
- **工具化**：15 个内置工具（日期时间 2 个 + 文件系统 10 个 + 网络搜索 1 个 + 网页抓取 1 个 + 本地命令行 1 个）通过注册中心统一管理；
- **可替换**：模型客户端遵循 `LLMClient` 协议，换服务商不改业务代码；
- **联网搜索**：`searchweb` 工具调用百度千帆「AI 搜索 - 网页搜索」API，返回网页标题、摘要片段与链接（每月 1500 次免费额度，不产生模型 token 费用）；
- **网页阅读**：`fetchweb` 工具调用本地 `curl` 下载网页，再按"精度 → 召回 → 标准库纯文本"三级降级提取正文并转换为 Markdown，导航首页也能提取到内容；
- **技能加载（Skills）**：从项目根目录的 `.agents/skills/` 动态发现技能，初始化只加载 `name` / `description`，完整指令经 `loadSkill` 工具按需惰性加载；
- **MCP Client**：启动时读取当前项目目录下的 `.mcp.json`，通过 Streamable HTTP 连接外部 MCP Server，把对方工具以「服务器名__工具名」前缀注入工具集，与本地工具统一参与 Function Calling，单个 Server 连不上只告警不影响其余工具；
- **可测试**：核心层与 TUI 层均有自动化测试（139 个用例，全部离线运行）；
- **兼容性强**：对服务商返回的畸形工具调用（参数碎片、缺调用 id、整段调用塞进参数）自动归一化。

## 快速开始

```powershell
cd Agent/tAgent

# 1. 安装依赖（Textual 为界面依赖；如需连接外部 MCP Server，附加 [mcp]）
pip install -e ".[tui,dev]"
# pip install -e ".[tui,dev,mcp]"   # 可选：启用 MCP Client

# 2. 准备配置（config.ini 已被 .gitignore 忽略）
copy config.example.ini config.ini   # Windows
# cp config.example.ini config.ini   # macOS / Linux
# 然后编辑 config.ini 填入 base_url / api_key / model
# 如需联网搜索，再填写 [search] 段的 baidu_qianfan_api_key

# 3. 启动终端界面
python -m tui
```

也可以直接用环境变量提供配置：

```powershell
$env:TAGENT_BASE_URL = "https://api.siliconflow.cn/v1"
$env:TAGENT_API_KEY = "<你的 API Key>"
$env:TAGENT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
$env:TAGENT_SEARCH_API_KEY = "<你的千帆搜索 API Key>"   # 可选：联网搜索
python -m tui
```

启动参数：

```powershell
python -m tui --model Qwen/Qwen2.5-7B-Instruct --base-url https://api.siliconflow.cn/v1
python -m tui --config D:\path\to\my.ini
```

## 界面操作

| 操作 | 快捷键 / 输入 |
| --- | --- |
| 发送 | `Enter` |
| 换行 | `Shift+Enter` / `Alt+Enter` |
| 清空对话 | `Ctrl+L` |
| 帮助 | `F1` |
| 退出 | `Ctrl+Q` |

斜杠命令（界面层功能，不消耗模型请求）：`/help`、`/clear`、`/tools`、`/model`、`/cwd`、`/exit`。

## 网络搜索

内置工具 `searchweb` 通过百度千帆「AI 搜索 - 网页搜索」API 获取互联网实时信息。
在 `config.ini` 中配置：

```ini
[search]
baidu_qianfan_api_key = <你的千帆 API Key>
edition = standard
timeout = 90
top_k = 10
```

- 接口为 `POST /v2/ai_search/web_search`，**只返回网页检索结果，不调用大模型生成摘要**，
  因此不产生模型 token 费用；每月有 1500 次免费额度（按天发放，优先抵扣免费资源）；
- `edition` 可选 `standard`（默认）/ `turbo` / `pro`，三者计费规则不同；
- 返回每条结果的标题、发布日期、URL 与摘要片段，需要阅读原文时模型会再用 `fetchweb` 抓取；
- query 超过 72 字符（汉字按 2 计）会自动截断，单条摘要超过 300 字会省略；
- 兼容旧配置名 `baidu_qianfan_key`，也可用环境变量 `TAGENT_SEARCH_API_KEY` 覆盖；
- API Key 为空时工具仍会注册，但会把“未配置”错误回传给模型；
- 网络超时、HTTP 错误、API 返回错误码都会转成清晰的中文错误。

API 文档：<https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5>

## 网页正文抓取

内置工具 `fetchweb` 用于阅读 `searchweb` 结果对应的原文，或抓取用户指定的网页：

- 通过参数列表调用本地 `curl`（不经过 shell），下载 HTML 后交由 `trafilatura` 提取正文；
- 输出 Markdown，保留标题、段落、列表、表格与链接，自动去除导航栏、广告和页脚；
- 正文过长时会截断，避免占用过多上下文；
- 需要系统已安装 `curl`（Windows 10+ 通常内置）；`trafilatura` 会随项目依赖自动安装；
- 抓取失败、超时、HTTP 错误、HTML 解析失败或无法提取正文时，都会返回清晰的中文错误；
- 仅抓取静态 HTML，不执行 JavaScript；对前端渲染的页面可能无法提取正文。

## 本地命令行调用

内置工具 `RunCli` 让 Agent 能够调用本机已安装的任意命令行程序（如 `python`、`git`、`ipconfig`）：

- 接收程序名 `command` 与参数列表 `args`，内部拼装为列表后以 `shell=False` 执行，不拼接 shell 命令字符串；
- `args` 推荐传数组；若模型传成一个字符串（如 `"config list"`）会按平台规则自动拆分（Windows 保留路径反斜杠、支持双引号包裹含空格的参数）；
- 子进程在工作线程中执行，不会阻塞 TUI / Web 界面的事件循环；
- 执行结果统一回传给模型：退出码（0 表示成功）、标准输出、标准错误，模型据此判断成败并决定下一步；
- 默认 60 秒执行超时（超时返回退出码 124），stdout / stderr 各自超过 8000 字符会截断并标明原始长度；
- 程序不存在时返回退出码 127，并提示如何调用 shell 内置命令（`dir`、`cd` 等）或 `.cmd`/`.bat` 程序（如 `npm`、`pip`）：经 `cmd /c`（Windows）/ `sh -c`（类 Unix）调用；
- **本阶段不设白名单、黑名单或审批，命令以运行 tAgent 的当前用户权限执行，仅限受控教学实验环境使用。**

## Skills（技能加载）

tAgent 支持以「技能（Skill）」为单位动态扩展能力：在**项目根目录**（默认启动时的工作目录）下创建 `.agentskills/` 目录，其中每个子目录对应一个 Skill，至少包含一个 `SKILL.md`：

```markdown
---
name: 技能名
description: 一句话说明该技能能做什么（供模型判断何时调用）
---
技能完整指令正文（模型通过 loadSkill 按需加载）
```

- **惰性加载**：初始化阶段只解析 `SKILL.md` 文件头的 YAML Frontmatter（`name` + `description`），完整正文不预读，由 `SkillSpec.body` 在模型实际需要时惰性读取；
- **零额外依赖**：核心层沿用「零第三方依赖」约定，内置一个只覆盖 Skill 元数据的极简 YAML Frontmatter 解析器；
- **自动发现**：`build_agent()` 默认以启动工作目录为项目根，自动发现并注册 `.agentskills` 里的 Skill；目录不存在或某个 Skill 无效时不会让启动失败，而是跳过并告警；
- **注入提示词**：发现的 Skill 的 `name` + `description` 会拼进 System Prompt，模型据此判断何时使用；
- **loadSkill 工具**：模型经 `loadSkill` 工具按名加载 Skill 的 `SKILL.md` 全文，或读取其附加文件（`filename` 支持相对技能目录、相对项目根或绝对路径，读取范围严格限制在技能目录内，越界路径一律拒绝）；
- 仅传 `name` 或传 `""` / `list` / `all` / `help` 时，返回当前全部可用技能清单。

## MCP（外部工具接入）

tAgent 内置一个 MCP Client，可以把任意**外部 MCP Server** 提供的工具，像本地工具一样注册给大模型做 Function Calling。使用官方 MCP Python SDK 的标准接口，当前支持 **Streamable HTTP** 协议。

### 配置：`.mcp.json`

启动 tAgent 时，会从**当前项目目录**（即你运行 `python -m tui` 时所在的目录，不是 tAgent 源码目录）下读取 `.mcp.json`，格式与 Claude / Cursor 等工具的 `mcpServers` 约定一致：

```json
{
  "mcpServers": {
    "Bazi-MCP": {
      "type": "streamable_http",
      "url": "https://example.com/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

- `type`：目前只支持 `streamable_http`（缺省也是它）；其他协议会被跳过并提示；
- `url`：MCP Server 地址，必填；
- `headers`：可选，需要鉴权时放 `Authorization` 等请求头；
- 该文件含个人端点 / token，已被 `.gitignore` 忽略，不会提交。

### 工作流程

1. **读配置**：`core/mcp/config.py` 同步读取 `.mcp.json`；文件不存在时视为没有外部 MCP，正常启动；
2. **发现工具**：TUI 启动的异步上下文中，`core/mcp/discovery.py` 依次连接每个 Server、调用 `list_tools()` 拿到工具名、描述与参数 JSON Schema；
3. **注册并加前缀**：为避免不同 Server 之间工具名冲突，暴露给模型的工具名统一为 `<服务器名>__<原始工具名>`（非法字符收敛为 `_`）；描述里也会标注「来自 MCP Server: xxx」；
4. **调用转发**：模型调用某前缀工具时，handler 按映射找到对应 Server，通过 `call_tool(原始工具名, 参数)` 转发，并把返回的文本内容（或结构化数据的文本表示）回传给模型；`isError` 响应会被标注为错误。

### 故障隔离

单个 MCP Server 连不上、超时、返回错误或不支持的协议时，只在聊天窗口输出一条 `[MCP] ...` 警告并跳过它，**不会阻断启动，也不影响本地工具与其他 Server**。这是「按需连接」模式：发现与每次调用都建立短期连接、用完即关。

## 目录结构

```text
tAgent/
├── core/                      # ── 核心层（无界面依赖）──────────────────
│   ├── config.py              #    配置加载（文件 + 环境变量）
│   ├── models.py              #    领域模型：Message / ToolCall
│   ├── events.py              #    对外事件定义
│   ├── session.py             #    会话状态（消息历史）
│   ├── agent.py               #    编排：模型 → 工具 → 模型
│   ├── factory.py             #    组装根：build_agent()
│   ├── errors.py              #    统一异常
│   ├── prompts.py             #    系统提示词
│   ├── llm/                   #    模型接入层
│   │   ├── client.py          #      LLMClient 协议
│   │   ├── openai_client.py   #      OpenAI 兼容实现（SSE 流式）
│   │   └── types.py           #      流式事件类型
│   ├── tools/                 #    工具体系
│   │   ├── base.py            #      ToolSpec / ToolResult
│   │   ├── registry.py        #      注册、参数校验、调用分发
│   │   └── builtin/           #      内置工具（datetime / filesystem / web_search / fetch_web）
│   ├── skills/                #    技能加载（Skill 发现 / 惰性读取 / loadSkill 工具）
│   ├── mcp/                   #    外部 MCP Client（配置读取 / Streamable HTTP 连接 / 工具发现与注册）
│   └── utils/                 #    通用工具（文本、文件）
├── tui/                       # ── Textual 终端界面 ─────────────────────
│   ├── app.py                 #    应用主体：事件 → 界面
│   ├── commands.py            #    斜杠命令
│   ├── theme.tcss             #    样式
│   └── widgets/               #    组件：对话区 / 输入框 / 状态栏
├── web/ desktop/ mobile/      # ── 预留的其他前端 ──────────────────────
├── docs/FRONTEND_CONTRACT.md  #    前端接入契约
├── tests/                     #    自动化测试
├── config.example.ini         #    配置模板
└── pyproject.toml
```

## 与 Practice02 的差异

| 维度 | `Practice02/file_chat.py` | `tAgent` |
| --- | --- | --- |
| 结构 | 单文件，模型调用 / 工具 / 界面混在一起 | `core` + `tui` 分层 |
| 界面 | `print` + `input` | Textual 终端界面（流式渲染、工具面板、状态栏） |
| I/O | 同步 `requests` | 异步 `httpx`（与前端事件循环一致） |
| 工具 | 模块级字典 | `ToolRegistry` + `ToolSpec`，可运行时注册 |
| 参数校验 | 无 | 注册中心统一校验必填项与类型 |
| 错误 | 打印到控制台 | 事件流（`ErrorRaised`）交给前端渲染 |
| 复用 | 只能跑命令行 | 同一套核心可接入 TUI / Web / Desktop / Mobile |
| 测试 | 无 | 139 个 pytest 用例（离线） |

## 测试

```powershell
cd Agent/tAgent
pip install -e ".[dev]"
pytest -q
```

测试全部使用假客户端与 `httpx.MockTransport`，**不会发起真实网络请求**，也不会读写项目外的文件。

## 扩展：新增一个前端

1. 新建目录（如 `web/`），只依赖 `core`；
2. `build_agent()` 拿到 Agent；
3. `async for event in agent.run(question)` 消费事件并渲染；
4. 事件语义见 [`docs/FRONTEND_CONTRACT.md`](docs/FRONTEND_CONTRACT.md)。

`web/`、`desktop/`、`mobile/` 三个目录已经放好了实现指引与目录约定，
可以按目录里的 README 直接开工。

## 安全提示

工具具备**创建、编辑、改名、删除本地文件与目录**、**联网搜索**以及**通过 RunCli
执行任意本地命令**的能力，且命令以当前用户权限运行、暂无白名单或审批机制。
请仅在受控教学实验环境、自己的练习目录下运行，不要指向重要数据目录；
`config.ini` 含模型与搜索密钥且已被 `.gitignore` 忽略，切勿提交。

## 许可证

学习与实验用途。
