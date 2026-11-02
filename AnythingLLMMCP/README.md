# anythingllm-mcp-server

基于 MCP 2026-07-28（Streamable HTTP）协议、连接本地 AnythingLLM 的极简 MCP Server。将「唯一工作区」的文档检索问答暴露为单个工具 `ask_workspace`。

## 需求

- Python 3.9+（仅标准库，零依赖）

## 运行

```bash
python server.py
```

默认监听 `http://127.0.0.1:8765/mcp`。

## 配置（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ANYTHINGLLM_BASE_URL` | `http://localhost:3001` | AnythingLLM 地址 |
| `ANYTHINGLLM_API_KEY` | 无（必填） | AnythingLLM API Key；未设置时启动直接报错退出 |
| `ANYTHINGLLM_SLUG` | 空 | 工作区 slug；为空时启动时自动探测第一个工作区 |
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `8765` | 监听端口 |

示例：

```bash
set ANYTHINGLLM_API_KEY=your-key
set PORT=9000
python server.py
```

## 客户端接入

只要支持 2026-07-28 Streamable HTTP 的 MCP 客户端，配置 URL 为 `http://127.0.0.1:8765/mcp` 即可。

## 手动测试

`tools/list`：

```bash
curl.exe -X POST http://127.0.0.1:8765/mcp ^
  -H "Content-Type: application/json" ^
  -H "MCP-Protocol-Version: 2026-07-28" ^
  -H "Mcp-Method: tools/list" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{\"_meta\":{\"io.modelcontextprotocol/protocolVersion\":\"2026-07-28\",\"io.modelcontextprotocol/clientCapabilities\":{}}}}"
```

`tools/call`：

```bash
curl.exe -X POST http://127.0.0.1:8765/mcp ^
  -H "Content-Type: application/json" ^
  -H "MCP-Protocol-Version: 2026-07-28" ^
  -H "Mcp-Method: tools/call" ^
  -H "Mcp-Name: ask_workspace" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"ask_workspace\",\"arguments\":{\"question\":\"胡芳是谁\"},\"_meta\":{\"io.modelcontextprotocol/protocolVersion\":\"2026-07-28\",\"io.modelcontextprotocol/clientCapabilities\":{}}}}"
```