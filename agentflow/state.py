"""StateGraph 式状态机：状态 + 条件边路由 + 节点级并行 + checkpoint 断点续传。

与 LangGraph StateGraph 的设计对齐：
- 状态为 dict，节点函数返回增量（update），执行器合并；
- 条件边（conditional edges）决定下一个节点；
- checkpoint 记录每个节点执行结果，支持断点续传 / 失败重试 / 幂等。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from .checkpoint import CheckpointStore
from .graph import Graph, Node

# 条件路由函数：async (state) -> bool（是否走这条边）
CondFn = Callable[[dict[str, Any]], Awaitable[bool]]


class StateGraphError(RuntimeError):
    pass


class StateGraph:
    """状态机式图编排。

    用法：
        g = StateGraph()
        g.add_node("a", fn_a)
        g.add_node("b", fn_b)
        g.add_edge("a", "b", condition=fn_cond)   # 条件边（可选）
        state = await g.run(initial, checkpoint=store)
    """

    def __init__(self, name: str = "state_graph") -> None:
        self.name = name
        self._graph = Graph(name)
        self._entry: str | None = None

    # ---------- 构建 ----------

    def add_node(
        self,
        name: str,
        fn: Any,
        description: str = "",
        retries: int = 0,
        timeout: float | None = None,
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

    @property
    def graph(self) -> Graph:
        return self._graph

    # ---------- 执行 ----------

    async def run(
        self,
        initial: dict[str, Any] | None = None,
        checkpoint: CheckpointStore | None = None,
        run_id: str | None = None,
        resume: bool = True,
        max_steps: int = 128,
    ) -> dict[str, Any]:
        """执行状态机。

        :param checkpoint: checkpoint 存储（None 则不持久化）
        :param run_id: 断点续传的 run id（为空时自动新建）
        :param resume: 是否恢复已成功节点（幂等执行）
        :param max_steps: 最大执行步数（防死循环）
        """
        from .checkpoint import new_run_id

        run_id = run_id or new_run_id()
        state = dict(initial or {})
        done: set[str] = set()

        if checkpoint is not None:
            if resume:
                saved = await checkpoint.nodes(run_id)
                state.update(await checkpoint.load(run_id))
                done = {n for n, m in saved.items() if m["status"] == "succeeded"}

        current = self._entry
        steps = 0
        while current is not None and steps < max_steps:
            steps += 1
            if current in done:
                # 幂等：跳过已成功节点
                current = await self._next_node(current, state)
                continue
            node = self._graph.nodes[current]
            try:
                inc = await self._run_with_retry(node, state)
                if not isinstance(inc, dict):
                    inc = {"result": inc}
                state.update(inc)
                if checkpoint is not None:
                    await checkpoint.save(run_id, current, "succeeded", inc)
            except Exception as exc:  # noqa: BLE001
                if checkpoint is not None:
                    await checkpoint.save(run_id, current, "failed", {}, str(exc))
                raise StateGraphError(f"节点 {current} 执行失败: {exc}") from exc
            done.add(current)
            current = await self._next_node(current, state)

        state["_run_id"] = run_id
        state["_executed_nodes"] = sorted(done)
        return state

    async def _run_with_retry(self, node: Node, state: dict[str, Any]) -> dict[str, Any]:
        """执行节点函数，支持失败重试（retries 次）。"""
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(node.retries + 1):
            try:
                if node.timeout is not None:
                    return await asyncio.wait_for(node.fn(state), node.timeout)
                return await node.fn(state)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        raise last_exc  # type: ignore[misc]

    async def _next_node(self, current: str, state: dict[str, Any]) -> str | None:
        """选择下一个节点：依次评估条件边，无条件边直接走。"""
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
