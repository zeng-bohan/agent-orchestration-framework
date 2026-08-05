"""pytest 共享夹具。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentflow.checkpoint import SQLiteCheckpointStore  # noqa: E402
from agentflow.llm import MockLLM  # noqa: E402
from agentflow.mcp.registry import Tool, ToolRegistry  # noqa: E402
from agentflow.mcp.transport import MCPServer  # noqa: E402


async def tool_add(a: int = 0, b: int = 0) -> int:
    """加法工具。"""
    return a + b


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(name="add", description="加法", parameters={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        }, fn=tool_add)
    )
    return reg


@pytest.fixture
def mcp_server(registry: ToolRegistry) -> MCPServer:
    return MCPServer(registry)


@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM()


@pytest.fixture
def checkpoint(tmp_path) -> SQLiteCheckpointStore:
    store = SQLiteCheckpointStore(str(tmp_path / "test.db"))
    return store
