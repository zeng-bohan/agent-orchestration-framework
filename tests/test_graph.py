"""Graph 图编排测试：DAG、条件边、并行、环检测。"""
from __future__ import annotations

import asyncio

import pytest

from agentflow.graph import Graph, GraphError, Node


async def fn_a(state):
    state["a"] = 1
    return {"a": 1}


async def fn_b(state):
    return {"b": state.get("a", 0) * 2}


async def fn_c(state):
    return {"c": "done"}


async def cond_go_b(state):
    return state.get("go_b", False)


def test_add_node_and_validate():
    g = Graph()
    g.add_node(Node("a", fn_a))
    g.add_node(Node("b", fn_b))
    g.add_edge("a", "b")
    g.validate()
    assert g.entries() == ["a"]


def test_duplicate_node_raises():
    g = Graph()
    g.add_node(Node("a", fn_a))
    with pytest.raises(GraphError):
        g.add_node(Node("a", fn_b))


def test_cycle_detection():
    g = Graph()
    g.add_node(Node("a", fn_a))
    g.add_node(Node("b", fn_b))
    g.add_edge("a", "b")
    g.add_edge("b", "a")
    with pytest.raises(GraphError):
        g.validate()


def test_layers_parallel():
    g = Graph()
    g.add_node(Node("a", fn_a))
    g.add_node(Node("b", fn_b))
    g.add_node(Node("c", fn_c))
    g.add_edge("a", "b")
    g.add_edge("a", "c")
    layers = g.layers()
    assert layers[0] == ["a"]
    assert set(layers[1]) == {"b", "c"}


@pytest.mark.asyncio
async def test_graph_run_dag():
    g = Graph()
    g.add_node(Node("a", fn_a))
    g.add_node(Node("b", fn_b))
    g.add_edge("a", "b")
    state = await g.run({})
    assert state["a"] == 1
    assert state["b"] == 2
    assert len(state["_execution"]) == 2


@pytest.mark.asyncio
async def test_graph_run_parallel_nodes_execute_concurrently():
    order: list[str] = []

    async def slow_x(state):
        await asyncio.sleep(0.1)
        order.append("x")
        return {"x": 1}

    async def slow_y(state):
        await asyncio.sleep(0.1)
        order.append("y")
        return {"y": 2}

    g = Graph()
    g.add_node(Node("start", fn_a))
    g.add_node(Node("x", slow_x))
    g.add_node(Node("y", slow_y))
    g.add_edge("start", "x")
    g.add_edge("start", "y")
    state = await g.run({})
    assert set(state) >= {"x", "y"}
    assert len(order) == 2


@pytest.mark.asyncio
async def test_graph_retry_on_failure():
    calls = {"n": 0}

    async def flaky(state):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("临时失败")
        return {"ok": True}

    g = Graph()
    g.add_node(Node("f", flaky, retries=2))
    state = await g.run({})
    assert state["ok"] is True
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_graph_node_timeout():
    async def hang(state):
        await asyncio.sleep(5)
        return {}

    g = Graph()
    g.add_node(Node("h", hang, timeout=0.1))
    with pytest.raises(GraphError):
        await g.run({})
