"""StateGraph 状态机 + checkpoint 持久化测试：断点续传 / 失败重试 / 幂等。"""
from __future__ import annotations

import pytest

from agentflow.checkpoint import SQLiteCheckpointStore
from agentflow.state import StateGraph, StateGraphError


async def node_a(state):
    return {"a": state.get("a", 0) + 1}


async def node_b(state):
    return {"b": f"b:{state.get('a', 0)}"}


async def node_fail(state):
    raise ValueError("模拟失败")


async def cond_to_b(state):
    return state.get("route") == "b"


def test_build_state_graph():
    g = StateGraph()
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge("a", "b", condition=cond_to_b)
    assert set(g.graph.nodes) == {"a", "b"}


@pytest.mark.asyncio
async def test_state_graph_sequential_run():
    g = StateGraph()
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge("a", "b")
    state = await g.run({"a": 1})
    assert state["a"] == 2
    assert state["b"] == "b:2"


@pytest.mark.asyncio
async def test_conditional_edge_routing():
    g = StateGraph()
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge("a", "b", condition=cond_to_b)
    # 条件不满足：a 执行后无后继
    state = await g.run({})
    assert state.get("a") == 1
    assert "b" not in state
    # 条件满足：路由到 b
    state = await g.run({"route": "b"})
    assert state.get("b") == "b:1"


@pytest.mark.asyncio
async def test_checkpoint_resume_skips_done_nodes(checkpoint: SQLiteCheckpointStore):
    g = StateGraph()
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge("a", "b")
    run_id = "run-resume-1"
    state = await g.run({"a": 10}, checkpoint=checkpoint, run_id=run_id)
    assert state["a"] == 11
    assert state["b"] == "b:11"
    # 第二次运行同 run_id：断点续传，a 已成功应跳过（a 不重复自增）
    state2 = await g.run({"a": 10}, checkpoint=checkpoint, run_id=run_id, resume=True)
    assert state2["a"] == 11  # 幂等：a 未重复执行
    assert state2["b"] == "b:11"


@pytest.mark.asyncio
async def test_checkpoint_failure_retry(checkpoint: SQLiteCheckpointStore):
    calls = {"n": 0}

    async def flaky(state):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("第一次失败")
        return {"ok": True}

    g = StateGraph()
    g.add_node("f", flaky, retries=1)
    g.add_node("b", node_b)
    g.add_edge("f", "b")
    state = await g.run({}, checkpoint=checkpoint, run_id="run-retry-1")
    assert state["ok"] is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_state_graph_failure_raises(checkpoint: SQLiteCheckpointStore):
    g = StateGraph()
    g.add_node("fail", node_fail)
    with pytest.raises(StateGraphError):
        await g.run({}, checkpoint=checkpoint, run_id="run-fail-1")
    # 失败节点被记录为 failed，可查询
    nodes = await checkpoint.nodes("run-fail-1")
    assert nodes["fail"]["status"] == "failed"
    assert "模拟失败" in nodes["fail"]["error"]


@pytest.mark.asyncio
async def test_checkpoint_state_reconstruction(checkpoint: SQLiteCheckpointStore):
    g = StateGraph()
    g.add_node("a", node_a)
    await g.run({}, checkpoint=checkpoint, run_id="run-state-1")
    loaded = await checkpoint.load("run-state-1")
    assert loaded["a"] == 1


@pytest.mark.asyncio
async def test_checkpoint_delete(checkpoint: SQLiteCheckpointStore):
    g = StateGraph()
    g.add_node("a", node_a)
    await g.run({}, checkpoint=checkpoint, run_id="run-del-1")
    assert await checkpoint.nodes("run-del-1")
    await checkpoint.delete("run-del-1")
    assert not await checkpoint.nodes("run-del-1")


@pytest.mark.asyncio
async def test_checkpoint_close_and_reopen(tmp_path):
    db = tmp_path / "reopen.db"
    store = SQLiteCheckpointStore(str(db))
    await store.save("r1", "a", "succeeded", {"x": 1})
    await store.close()
    # 重新打开同一文件：数据仍在
    store2 = SQLiteCheckpointStore(str(db))
    nodes = await store2.nodes("r1")
    assert nodes["a"]["status"] == "succeeded"
    assert nodes["a"]["state"] == {"x": 1}
    await store2.close()


@pytest.mark.asyncio
async def test_checkpoint_new_run_id():
    from agentflow.checkpoint import new_run_id

    a, b = new_run_id(), new_run_id()
    assert a != b
    assert a.startswith("run_")


@pytest.mark.asyncio
async def test_state_graph_without_checkpoint():
    """无 checkpoint 时正常执行且不持久化。"""
    g = StateGraph()
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge("a", "b")
    state = await g.run({})
    assert state["a"] == 1
    assert "b" in state


@pytest.mark.asyncio
async def test_state_graph_resume_false_reruns(checkpoint: SQLiteCheckpointStore):
    """resume=False 时重跑全部节点（a 重复自增）。"""
    g = StateGraph()
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge("a", "b")
    await g.run({"a": 1}, checkpoint=checkpoint, run_id="run-false-1")
    state2 = await g.run({"a": 1}, checkpoint=checkpoint, run_id="run-false-1", resume=False)
    assert state2["a"] == 2  # 未恢复：a 再次执行
    assert state2["b"] == "b:2"
