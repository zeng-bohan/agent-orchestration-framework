"""DAG 图编排：节点、边、条件路由。

设计要点：
- 节点（Node）：名称 + 执行函数（async fn(state) -> state 增量）。
- 边：普通边（a -> b）与条件边（a -> b/c，按条件函数路由）。
- 执行：按拓扑序逐节点执行（v1：顺序执行，后续版本引入分层并行）。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

NodeFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
RouteFn = Callable[[dict[str, Any]], Awaitable[str]]


class GraphError(RuntimeError):
    pass


@dataclass
class Node:
    name: str
    fn: NodeFn
    description: str = ""
    retries: int = 0
    timeout: float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise GraphError("节点名不能为空")
        if not asyncio.iscoroutinefunction(self.fn):
            raise GraphError(f"节点 {self.name} 的执行函数必须是 async 函数")


@dataclass
class Edge:
    source: str
    target: str
    condition: RouteFn | None = None

    @property
    def is_conditional(self) -> bool:
        return self.condition is not None


class Graph:
    def __init__(self, name: str = "graph") -> None:
        self.name = name
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._adj: dict[str, list[Edge]] = defaultdict(list)

    def add_node(self, node: Node) -> "Graph":
        if node.name in self._nodes:
            raise GraphError(f"节点已存在: {node.name}")
        self._nodes[node.name] = node
        return self

    def add_edge(self, source: str, target: str, condition: RouteFn | None = None) -> "Graph":
        if source not in self._nodes:
            raise GraphError(f"源节点不存在: {source}")
        if target not in self._nodes:
            raise GraphError(f"目标节点不存在: {target}")
        edge = Edge(source=source, target=target, condition=condition)
        self._edges.append(edge)
        self._adj[source].append(edge)
        return self

    def validate(self) -> None:
        if not self._nodes:
            raise GraphError("图为空")
        indeg = {n: 0 for n in self._nodes}
        for e in self._edges:
            indeg[e.target] += 1
        q = deque([n for n, d in indeg.items() if d == 0])
        if not q:
            raise GraphError("图中存在环：无起点节点")
        visited = 0
        while q:
            n = q.popleft()
            visited += 1
            for e in self._adj[n]:
                indeg[e.target] -= 1
                if indeg[e.target] == 0:
                    q.append(e.target)
        if visited != len(self._nodes):
            raise GraphError("图中存在环")

    async def run(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = dict(state or {})
        self.validate()
        # 拓扑序（同层内按注册顺序执行）
        indeg = {n: 0 for n in self._nodes}
        for e in self._edges:
            indeg[e.target] += 1
        q = deque(sorted([n for n, d in indeg.items() if d == 0]))
        order: list[str] = []
        while q:
            n = q.popleft()
            order.append(n)
            for e in self._adj[n]:
                indeg[e.target] -= 1
                if indeg[e.target] == 0:
                    q.append(e.target)
        results = []
        for name in order:
            node = self._nodes[name]
            try:
                if node.timeout:
                    inc = await asyncio.wait_for(node.fn(state), node.timeout)
                else:
                    inc = await node.fn(state)
                if not isinstance(inc, dict):
                    inc = {"result": inc}
                state.update(inc)
                results.append({"node": name, "status": "succeeded"})
            except Exception as exc:
                results.append({"node": name, "status": "failed", "error": str(exc)})
                raise GraphError(f"节点 {name} 执行失败: {exc}") from exc
        state["_execution"] = results
        return state
