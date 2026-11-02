import base64
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTOCOL_VERSION = "2026-07-28"
SERVER_INFO = {"name": "anythingllm-mcp-server", "version": "0.1.0"}

BASE_URL = os.environ.get("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
API_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "").strip()
if not API_KEY:
    sys.exit("缺少环境变量 ANYTHINGLLM_API_KEY，请先设置 AnythingLLM 后台的 API Key 再启动")
FIXED_SLUG = os.environ.get("ANYTHINGLLM_SLUG", "").strip() or None
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))

TOOL = {
    "name": "ask_workspace",
    "title": "AnythingLLM 工作区问答",
    "description": (
        "基于本地 AnythingLLM 唯一工作区中的文档，检索相关内容并回答用户的问题。"
        "适用于询问工作区文档中包含的事实或信息。"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "要向工作区文档提出的问题",
            }
        },
        "required": ["question"],
        "additionalProperties": False,
    },
}


def _http_json(method, path, payload=None, timeout=180):
    headers = {"Authorization": "Bearer %s" % API_KEY}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return None, "AnythingLLM HTTP %s: %s" % (exc.code, detail)
    except Exception as exc:
        return None, "AnythingLLM 调用失败: %s" % exc


def resolve_slug():
    if FIXED_SLUG:
        return FIXED_SLUG
    data, err = _http_json("GET", "/api/v1/workspaces")
    if err or not data or not data.get("workspaces"):
        return None
    return data["workspaces"][0]["slug"]


WORKSPACE_SLUG = resolve_slug()


def query_workspace(question):
    if not WORKSPACE_SLUG:
        return None, "未解析到 AnythingLLM 工作区，请检查服务与 ANYTHINGLLM_SLUG 配置"
    data, err = _http_json(
        "POST",
        "/api/v1/workspace/%s/chat" % WORKSPACE_SLUG,
        {"message": question, "mode": "query", "sessionId": "mcp"},
    )
    if err:
        return None, err
    if data.get("error"):
        return None, "AnythingLLM: %s" % data["error"]
    return data.get("textResponse") or "", None


def decode_header_value(value):
    if value.startswith("=?base64?") and value.endswith("?="):
        try:
            return base64.b64decode(value[len("=?base64?"):-2]).decode("utf-8")
        except Exception:
            return None
    return value


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def _send(self, code, obj=None):
        body = b""
        if obj is not None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _error(self, code, rpc_id, err_code, message, data=None):
        err = {"code": err_code, "message": message}
        if data is not None:
            err["data"] = data
        body = {"jsonrpc": "2.0", "error": err}
        if rpc_id is not None:
            body["id"] = rpc_id
        self._send(code, body)

    def _result(self, rpc_id, result):
        result["_meta"] = {"io.modelcontextprotocol/serverInfo": SERVER_INFO}
        self._send(200, {"jsonrpc": "2.0", "id": rpc_id, "result": result})

    def do_GET(self):
        self._send(405)

    do_DELETE = do_GET

    def _validate(self, msg):
        rpc_id = msg.get("id")
        params = msg.get("params") or {}
        meta = params.get("_meta") or {}
        version_hdr = self.headers.get("MCP-Protocol-Version")
        if not version_hdr:
            return {"code": -32020, "message": "Missing required MCP-Protocol-Version header", "rpc_id": rpc_id}
        if version_hdr != PROTOCOL_VERSION:
            return {
                "code": -32022,
                "message": "Unsupported protocol version: %s" % version_hdr,
                "data": {"supported": [PROTOCOL_VERSION]},
                "rpc_id": rpc_id,
            }
        if meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL_VERSION:
            return {"code": -32020, "message": "MCP-Protocol-Version header does not match _meta", "rpc_id": rpc_id}
        if "io.modelcontextprotocol/clientCapabilities" not in meta:
            return {
                "code": -32602,
                "message": "Missing required _meta field: io.modelcontextprotocol/clientCapabilities",
                "rpc_id": rpc_id,
            }
        if self.headers.get("Mcp-Method") != msg.get("method"):
            return {"code": -32020, "message": "Mcp-Method header does not match body method", "rpc_id": rpc_id}
        if msg.get("method") == "tools/call":
            name = params.get("name")
            mcp_name = decode_header_value(self.headers.get("Mcp-Name", ""))
            if not mcp_name or mcp_name != name:
                return {"code": -32020, "message": "Mcp-Name header does not match body name", "rpc_id": rpc_id}
        return None

    def _handle_list(self, rpc_id, params):
        self._result(rpc_id, {"resultType": "complete", "tools": [TOOL]})

    def _handle_call(self, rpc_id, params):
        name = params.get("name")
        if name != TOOL["name"]:
            self._error(400, rpc_id, -32602, "Unknown tool: %s" % name)
            return
        question = (params.get("arguments") or {}).get("question")
        if not isinstance(question, str) or not question.strip():
            self._error(400, rpc_id, -32602, "Missing required argument: question")
            return
        text, err = query_workspace(question.strip())
        if err:
            self._result(
                rpc_id,
                {
                    "resultType": "complete",
                    "content": [{"type": "text", "text": err}],
                    "isError": True,
                },
            )
            return
        self._result(
            rpc_id,
            {
                "resultType": "complete",
                "content": [{"type": "text", "text": text}],
                "isError": False,
            },
        )

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin:
            host = origin.split("://", 1)[-1].split("/", 1)[0]
            host = host.lstrip("[")
            if host.split(":", 1)[0] not in ("localhost", "127.0.0.1", "::1"):
                self._error(403, None, -32600, "Forbidden: invalid Origin header")
                return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 1024 * 1024:
                self._error(400, None, -32600, "Invalid request body size")
                return
            msg = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(msg, dict):
                raise ValueError()
        except Exception:
            self._error(400, None, -32700, "Parse error")
            return
        rpc_id = msg.get("id")
        if rpc_id is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            invalid = self._validate(msg)
            if invalid:
                self._error(
                    400,
                    invalid["rpc_id"],
                    invalid["code"],
                    invalid["message"],
                    invalid.get("data"),
                )
                return
            method = msg.get("method")
            if method == "tools/list":
                self._handle_list(rpc_id, msg.get("params") or {})
            elif method == "tools/call":
                self._handle_call(rpc_id, msg.get("params") or {})
            else:
                self._error(404, rpc_id, -32601, "Method not found: %s" % method)
        except Exception as exc:
            self._error(500, rpc_id, -32603, "Internal error: %s" % exc)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("MCP server listening on http://%s:%s/mcp" % (HOST, PORT), flush=True)
    if WORKSPACE_SLUG:
        print("Using AnythingLLM workspace: %s" % WORKSPACE_SLUG, flush=True)
    else:
        print("WARNING: could not resolve AnythingLLM workspace", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()