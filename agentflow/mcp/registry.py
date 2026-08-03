"""MCP 兼容工具注册中心（v1：基础注册与调用）。

- 工具注册：名称 / 描述 / 参数 JSON Schema / 异步执行函数；
- 协议：tools/list / tools/call（与 MCP 标准对齐），供 stdio / SSE Transport 复用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

ToolFn = Callable[..., Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            },
        }


class ToolRegistryError(RuntimeError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolRegistryError(f"工具已存在: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def list_schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self.list()]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        tool = self.get(name)
        if tool is None:
            raise ToolRegistryError(f"工具不存在: {name}")
        return await tool.fn(**(arguments or {}))
