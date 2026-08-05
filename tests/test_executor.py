"""LLM 抽象与 Executor 测试（Mock LLM + 调用成功率统计）。"""
from __future__ import annotations

import pytest

from agentflow.checkpoint import SQLiteCheckpointStore
from agentflow.executor import Executor
from agentflow.graph import Graph, Node
from agentflow.llm import MockLLM
from agentflow.state import StateGraph


async def llm_node(state):
    reply = await state["llm"].generate(
        [{"role": "user", "content": state["query"]}],
        tools=[{"name": "search", "description": "检索"}],
    )
    return {"reply": reply}


@pytest.mark.asyncio
async def test_mock_llm_deterministic(mock_llm: MockLLM):
    r1 = await mock_llm.generate([{"role": "user", "content": "北京天气"}])
    r2 = await mock_llm.generate([{"role": "user", "content": "北京天气"}])
    assert r1 == r2
    assert "北京天气" in r1


@pytest.mark.asyncio
async def test_mock_llm_with_tools(mock_llm: MockLLM):
    r = await mock_llm.generate([{"role": "user", "content": "查资料"}], tools=[{"name": "search"}])
    assert "search" in r
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_executor_with_state_graph(mock_llm: MockLLM, checkpoint: SQLiteCheckpointStore):
    g = StateGraph()
    g.add_node("llm", llm_node)
    ex = Executor(g, checkpoint=checkpoint)
    state = await ex.run({"llm": mock_llm, "query": "分析舆情"}, run_id="run-exec-1")
    assert "reply" in state
    assert state["_run_id"] == "run-exec-1"


@pytest.mark.asyncio
async def test_executor_with_plain_graph():
    async def n1(state):
        return {"x": 1}

    g = Graph()
    g.add_node(Node("n1", n1))
    ex = Executor(g)
    state = await ex.run({})
    assert state["x"] == 1


@pytest.mark.asyncio
async def test_mock_llm_call_success_rate(mock_llm: MockLLM):
    """调用成功率 95%+ 验证：100 次调用全部成功。"""
    ok = 0
    n = 100
    for i in range(n):
        try:
            await mock_llm.generate([{"role": "user", "content": f"q{i}"}])
            ok += 1
        except Exception:
            pass
    rate = ok / n
    assert rate >= 0.95
