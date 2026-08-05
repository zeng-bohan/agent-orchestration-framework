"""MCP 工具注册中心 / Transport / Skills 发现测试。"""
from __future__ import annotations

import json

import pytest

from agentflow.mcp.registry import Tool, ToolRegistry, ToolRegistryError, load_python_tools
from agentflow.mcp.transport import MCPServer, SSETransport, StdioTransport


# ---------- 注册中心：热插拔与版本管理 ----------

def test_register_and_call(registry: ToolRegistry):
    assert registry.get("add") is not None
    assert len(registry.list()) == 1


@pytest.mark.asyncio
async def test_call_tool(registry: ToolRegistry):
    result = await registry.call("add", {"a": 2, "b": 3})
    assert result == 5


def test_hot_swap_update_version(registry: ToolRegistry):
    v1 = registry.get("add").version
    registry.update("add", Tool(name="add", description="加法v2", parameters={}, fn=lambda **k: 0))
    v2 = registry.get("add").version
    assert v2 != v1
    assert registry.versions("add")[0] == v2


def test_rollback_version(registry: ToolRegistry):
    registry.update("add", Tool(name="add", description="v2", parameters={}, fn=lambda **k: 0))
    prev = registry.rollback("add")
    assert prev is not None
    assert registry.get("add").version == prev.version


def test_unregister(registry: ToolRegistry):
    registry.unregister("add")
    assert registry.get("add") is None
    with pytest.raises(ToolRegistryError):
        registry.unregister("add")


@pytest.mark.asyncio
async def test_call_unknown_tool_raises(registry: ToolRegistry):
    with pytest.raises(ToolRegistryError):
        await registry.call("nope")


# ---------- Skills 动态发现 ----------

def test_discover_skills(tmp_path):
    skills = tmp_path / "skills"
    (skills / "web-search").mkdir(parents=True)
    (skills / "web-search" / "SKILL.md").write_text(
        "---\nname: web-search\ndescription: 网页搜索技能\n---\n\n# Web Search\n执行搜索。",
        encoding="utf-8",
    )
    reg = ToolRegistry()
    n = reg.discover_skills(str(skills))
    assert n == 1
    tool = reg.get("skill_web-search")
    assert tool is not None
    assert "网页搜索" in tool.description


def test_load_python_tools(tmp_path):
    mod = tmp_path / "mytools.py"
    mod.write_text(
        '\nasync def tool_hello(name: str = "world") -> str:\n'
        '    """打招呼工具。"""\n'
        '    return f"hello {name}"\n',
        encoding="utf-8",
    )
    tools = load_python_tools(str(mod))
    assert len(tools) == 1
    assert tools[0].name == "hello"


# ---------- MCPServer / Transport ----------

def test_mcp_initialize(mcp_server: MCPServer):
    resp = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "t"}}}
    )
    # 同步方法返回 coroutine 时同步执行
    if hasattr(resp, "__await__"):
        import asyncio

        resp = asyncio.run(resp)
    assert resp["result"]["protocolVersion"] == "2024-11-05"


@pytest.mark.asyncio
async def test_mcp_tools_list(mcp_server: MCPServer):
    resp = await mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert resp["result"]["tools"][0]["name"] == "add"


@pytest.mark.asyncio
async def test_mcp_tools_call(mcp_server: MCPServer):
    resp = await mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "add", "arguments": {"a": 1, "b": 2}},
        }
    )
    content = resp["result"]["content"][0]["text"]
    assert json.loads(content) == 3


@pytest.mark.asyncio
async def test_mcp_unknown_method(mcp_server: MCPServer):
    resp = await mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "bogus"})
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_ping_and_notification(mcp_server: MCPServer):
    resp = await mcp_server.handle({"jsonrpc": "2.0", "id": 5, "method": "ping"})
    assert resp["result"] == {}
    # 通知无需响应
    resp = await mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp == {}


@pytest.mark.asyncio
async def test_mcp_call_without_name(mcp_server: MCPServer):
    resp = await mcp_server.handle(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"arguments": {}}}
    )
    assert resp["error"]["code"] == -32000


@pytest.mark.asyncio
async def test_mcp_call_tool_error(mcp_server: MCPServer, registry: ToolRegistry):
    async def boom(**kwargs):
        raise ValueError("工具内部错误")

    registry.register(Tool(name="boom", description="坏工具", parameters={}, fn=boom))
    resp = await mcp_server.handle(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "boom"}}
    )
    assert resp["error"]["code"] == -32000


def test_stdio_transport_creatable(registry: ToolRegistry):
    server = MCPServer(registry)
    t = StdioTransport(server)
    assert t.server is server


def test_sse_transport_stream(registry: ToolRegistry):
    server = MCPServer(registry)
    t = SSETransport(server)
    sid, q = t.create_stream()
    assert q is not None
    t.close_stream(sid)


@pytest.mark.asyncio
async def test_sse_transport_push(mcp_server: MCPServer):
    t = SSETransport(mcp_server)
    sid, q = t.create_stream()
    resp = await t.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "add", "arguments": {"a": 5, "b": 5}},
        },
        stream_id=sid,
    )
    assert resp == {"accepted": True}
    pushed = await q.get()
    assert json.loads(pushed["result"]["content"][0]["text"]) == 10
