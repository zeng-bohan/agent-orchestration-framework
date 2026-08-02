"""StateGraph 式状态机：状态 + 条件边路由（v1：无 checkpoint 持久化）。

与 LangGraph StateGraph 的设计对齐：
- 状态为 dict，节点函数返回增量（update），执行器合并；
- 条件边（conditional edges）决定下一个节点。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from .graph import Graph, Node

CondFn = Callable[[dict[str, Any]], Awaitable[bool]]


class StateGraphError(RuntimeError):
    pass


class StateGraph:
    def __init__(self, name: str = "state_graph") -> None:
        self.name = name
        self._graph = Graph(name)
        self._entry: str | None = None

    def add_node(
        self, name: str, fn: Any, description: str = "",
        retries: int = 0, timeout: float | None = None,
    ) -> "StateGraph":
        self._graph.add_node(
            Node(name=name, fn=fn, description=description, retries=retries, timeout=timeout)
        )
        if self._entry is None:
            self._entry = name
        return self

    def set_entry(self, name: str) -> "StateGraph":
        if name not in self._graph.nodes:
            raise StateGraphError(f"入口节点不存在: {name}")
        self._entry = name
        return self

    def add_edge(self, source: str, target: str, condition: CondFn | None = None) -> "StateGraph":
        self._graph.add_edge(source, target, condition=condition)
        return self

    async def run(self, initial: dict[str, Any] | None = None, max_steps: int = 128) -> dict[str, Any]:
        state = dict(initial or {})
        current = self._entry
        steps = 0
        done: set[str] = set()
        while current is not None and steps < max_steps:
            steps += 1
            node = self._graph.nodes[current]
            inc = await node.fn(state)
            if not isinstance(inc, dict):
                inc = {"result": inc}
            state.update(inc)
            done.add(current)
            current = await self._next_node(current, state)
        state["_run_id"] = ""
        state["_executed_nodes"] = sorted(done)
        return state

    async def _next_node(self, current: str, state: dict[str, Any]) -> str | None:
        edges = self._graph.successors(current)
        for edge in edges:
            if edge.condition is None:
                return edge.target
            try:
                if await edge.condition(state):
                    return edge.target
            except Exception:
                continue
        return None
