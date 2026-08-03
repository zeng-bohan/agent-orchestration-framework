"""Executor：图/状态机的执行器（Graph.run / StateGraph.run 的上层封装）。"""
from __future__ import annotations

from typing import Any

from .checkpoint import CheckpointStore, SQLiteCheckpointStore
from .graph import Graph, Node
from .state import StateGraph


class Executor:
    """统一执行入口：Graph 与 StateGraph 皆可执行，支持 checkpoint。"""

    def __init__(self, graph: Graph | StateGraph, checkpoint: CheckpointStore | None = None) -> None:
        if isinstance(graph, StateGraph):
            self._graph = graph.graph
            self._state_graph = graph
        else:
            self._graph = graph
            self._state_graph = None
        self.checkpoint = checkpoint

    async def run(
        self,
        initial: dict[str, Any] | None = None,
        run_id: str | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        if self._state_graph is not None:
            return await self._state_graph.run(
                initial=initial, checkpoint=self.checkpoint, run_id=run_id, resume=resume
            )
        return await self._graph.run(initial)
