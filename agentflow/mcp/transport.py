"""MCP Transport：stdio / SSE 两种传输，提供 MCP 兼容的 JSON-RPC 服务。

实现 MCP 协议核心方法：
- initialize：协议握手（协议版本 / 能力 / 服务器信息）
- tools/list：列出已注册工具
- tools/call：调用工具
- ping：心跳
- notifications/initialized：初始化完成通知

- StdioTransport：子进程 stdin/stdout 行协议（JSON-RPC 2.0 over stdio）
- SSETransport：HTTP Server-Sent Events（POST 请求 + GET 事件流）
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from .registry import ToolRegistry

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agentflow-mcp", "version": "0.1.0"}


class MCPServer:
    """MCP 服务核心：JSON-RPC 2.0 分发。"""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.client_info: dict[str, Any] = {}
        self.session_id: str = uuid.uuid4().hex

    async def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        """处理一条 JSON-RPC 请求，返回响应。"""
        method = message.get("method")
        params = message.get("params") or {}
        msg_id = message.get("id")

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "tools/list":
                result = {"tools": self.registry.list_schemas()}
            elif method == "tools/call":
                result = await self._call_tool(params)
            elif method == "ping":
                result = {}
            elif method == "notifications/initialized":
                return {}  # 通知无需响应
            else:
                return self._error(msg_id, -32601, f"未知方法: {method}")
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except Exception as exc:  # noqa: BLE001
            return self._error(msg_id, -32000, str(exc))

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self.client_info = params.get("clientInfo", {})
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }

    async def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            raise ValueError("缺少工具名")
        result = await self.registry.call(name, arguments)
        if isinstance(result, dict):
            text = json.dumps(result, ensure_ascii=False)
        elif isinstance(result, str):
            text = result
        else:
            text = str(result)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }


class StdioTransport:
    """stdio Transport：子进程通过 stdin/stdout 与服务器通信（JSON-RPC over stdio）。"""

    def __init__(self, server: MCPServer) -> None:
        self.server = server

    async def serve(self) -> None:
        """持续读取 stdin 行，处理请求并写回 stdout。"""
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, self._readline)
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = await self.server.handle(message)
            if response:
                print(json.dumps(response, ensure_ascii=False), flush=True)

    @staticmethod
    def _readline() -> str | None:
        import sys

        line = sys.stdin.readline()
        return line if line else None


class SSETransport:
    """SSE Transport：HTTP POST（请求）+ GET 事件流（结果）。

    - POST /mcp：JSON-RPC 请求，立即返回响应
    - GET /mcp/stream：SSE 事件流（保持连接，接收服务端推送）
    简化实现：服务端通过 event queue 推送工具调用结果。
    """

    def __init__(self, server: MCPServer) -> None:
        self.server = server
        self._streams: dict[str, asyncio.Queue] = {}
        self._next_stream_id = 0

    def create_stream(self) -> tuple[str, asyncio.Queue]:
        """创建事件流，返回 (stream_id, queue)。"""
        sid = f"stream-{self._next_stream_id}"
        self._next_stream_id += 1
        q: asyncio.Queue = asyncio.Queue()
        self._streams[sid] = q
        return sid, q

    def close_stream(self, stream_id: str) -> None:
        self._streams.pop(stream_id, None)

    async def handle_request(self, body: dict[str, Any], stream_id: str | None = None) -> dict[str, Any]:
        """处理 POST 请求；若指定 stream_id，将结果推送到事件流。"""
        response = await self.server.handle(body)
        if stream_id and stream_id in self._streams and response:
            await self._streams[stream_id].put(response)
            return {"accepted": True}
        return response
