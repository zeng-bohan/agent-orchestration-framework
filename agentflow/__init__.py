"""agentflow — 轻量 Agent 编排框架。

支持 DAG 图编排、条件边路由、节点级并行调度、StateGraph 状态机、
SQLite checkpoint 持久化（断点续传 / 失败重试 / 幂等执行）、
MCP 兼容工具注册中心（stdio / SSE Transport）与 Skills 动态发现。
"""
from .checkpoint import CheckpointStore, SQLiteCheckpointStore, new_run_id
from .executor import Executor
from .graph import Edge, Graph, GraphError, Node, NodeResult
from .llm import BaseLLM, MockLLM
from .state import StateGraph, StateGraphError
from .mcp.registry import Tool, ToolRegistry, ToolRegistryError
from .mcp.transport import MCPServer, SSETransport, StdioTransport

__all__ = [
    "Graph",
    "Edge",
    "Node",
    "NodeResult",
    "GraphError",
    "StateGraph",
    "StateGraphError",
    "Executor",
    "CheckpointStore",
    "SQLiteCheckpointStore",
    "new_run_id",
    "BaseLLM",
    "MockLLM",
    "Tool",
    "ToolRegistry",
    "ToolRegistryError",
    "MCPServer",
    "StdioTransport",
    "SSETransport",
]

__version__ = "0.1.0"
