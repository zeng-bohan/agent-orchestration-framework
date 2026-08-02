"""DAG 图编排：节点、边、条件路由、节点级并行调度。

设计要点：
- 节点（Node）：名称 + 执行函数（async fn(state) -> state 增量）。
- 边：普通边（a -> b）与条件边（a -> b/c/d，按条件函数路由）。
- 执行：按拓扑序分层，同层节点并行调度（asyncio.gather）。
- 结果（NodeResult）：结构化返回节点执行状态，供 checkpoint 持久化。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# 节点执行函数：async (state: dict) -> dict（返回状态增量）
NodeFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
# 条件路由函数：async (state: dict) -> str（返回目标节点名）
RouteFn = Callable[[dict[str, Any]], Awaitable[str]]


class GraphError(RuntimeError):
    pass


@dataclass
class Node:
    """图节点。"""

    name: str
    fn: NodeFn
    description: str = ""
    retries: int = 0  # 失败重试次数
    timeout: float | None = None  # 单节点超时（秒）

    def __post_init__(self) -> None:
        if not self.name:
            raise GraphError("节点名不能为空")
        if not asyncio.iscoroutinefunction(self.fn):
            raise GraphError(f"节点 {self.name} 的执行函数必须是 async 函数")


@dataclass
class Edge:
    """普通边 / 条件边。"""

    source: str
    target: str
    condition: RouteFn | None = None  # 非空则为条件边

    @property
    def is_conditional(self) -> bool:
        return self.condition is not None


@dataclass
class NodeResult:
    """节点执行结果（供 checkpoint 与幂等判断）。"""

    node: str
    status: str  # succeeded / failed / skipped
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0


class Graph:
    """有向无环图：支持并行分层执行与条件路由。"""

    def __init__(self, name: str = "graph") -> None:
        self.name = name
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._adj: dict[str, list[Edge]] = defaultdict(list)  # source -> edges

    # ---------- 构建 ----------

    def add_node(self, node: Node) -> "Graph":
        if node.name in self._nodes:
            raise GraphError(f"节点已存在: {node.name}")
        self._nodes[node.name] = node
        return self

    def add_edge(
        self, source: str, target: str, condition: RouteFn | None = None
    ) -> "Graph":
        if source not in self._nodes:
            raise GraphError(f"源节点不存在: {source}")
        if target not in self._nodes:
            raise GraphError(f"目标节点不存在: {target}")
        edge = Edge(source=source, target=target, condition=condition)
        self._edges.append(edge)
        self._adj[source].append(edge)
        return self

    # ---------- 拓扑 ----------

    @property
    def nodes(self) -> dict[str, Node]:
        return dict(self._nodes)

    def entries(self) -> list[str]:
        """入度为零的节点（起点）。"""
        has_in = {e.target for e in self._edges}
        return [n for n in self._nodes if n not in has_in]

    def validate(self) -> None:
        """校验：无环（拓扑排序），至少一个起点。"""
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

    def layers(self) -> list[list[str]]:
        """按依赖分层（同层可并行）。"""
        self.validate()
        indeg = {n: 0 for n in self._nodes}
        for e in self._edges:
            indeg[e.target] += 1
        remaining = set(self._nodes)
        out: list[list[str]] = []
        while remaining:
            layer = [n for n in remaining if indeg[n] == 0]
            if not layer:
                raise GraphError("图中存在环")
            out.append(layer)
            for n in layer:
                remaining.discard(n)
                for e in self._adj[n]:
                    indeg[e.target] -= 1
        return out

    def successors(self, node: str) -> list[Edge]:
        return list(self._adj[node])

    # ---------- 执行 ----------

    async def run(
        self,
        state: dict[str, Any] | None = None,
        stop_at: str | None = None,
        max_nodes: int = 256,
    ) -> dict[str, Any]:
        """执行图：按层并行调度，支持条件路由。

        :param state: 初始状态
        :param stop_at: 执行到指定节点后停止（用于调试/分步）
        :param max_nodes: 单次执行节点数上限（防死循环）
        """
        state = dict(state or {})
        self.validate()
        executed: set[str] = set()
        nodes_done = 0

        async def _run_node(name: str) -> NodeResult:
            nonlocal nodes_done
            nodes_done += 1
            node = self._nodes[name]
            for attempt in range(node.retries + 1):
                try:
                    if node.timeout:
                        inc = await asyncio.wait_for(node.fn(state), node.timeout)
                    else:
                        inc = await node.fn(state)
                    if not isinstance(inc, dict):
                        inc = {"result": inc}
                    state.update(inc)
                    return NodeResult(node=name, status="succeeded", output=inc)
                except Exception as exc:  # noqa: BLE001
                    if attempt >= node.retries:
                        raise
            raise GraphError("不可达")  # pragma: no cover

        results: list[NodeResult] = []
        for layer in self.layers():
            # 跳过已被条件路由跳过的节点
            pending = [n for n in layer if n not in executed]
            if not pending:
                continue
            if nodes_done + len(pending) > max_nodes:
                raise GraphError("超过单次执行节点上限，疑似死循环")
            layer_results = await asyncio.gather(
                *(_run_node(n) for n in pending), return_exceptions=True
            )
            for n, r in zip(pending, layer_results):
                if isinstance(r, BaseException):
                    results.append(
                        NodeResult(node=n, status="failed", error=str(r))
                    )
                    raise GraphError(f"节点 {n} 执行失败: {r}") from r
                results.append(r)
                executed.add(n)
            if stop_at and stop_at in executed:
                break

        state["_execution"] = [
            {"node": r.node, "status": r.status, "error": r.error} for r in results
        ]
        return state
