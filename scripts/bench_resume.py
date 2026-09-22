"""断点续传基准：量化 StateGraph resume 语义的收益。

一条命令复现：python scripts/bench_resume.py

构造 N 节点线性流水线，在第 k 个节点注入失败后：
- 全量重跑：全新 run_id 从头执行（等价无 checkpoint 场景）；
- resume：同 run_id 恢复，仅重跑失败节点及其后继。

输出两种路径的节点执行数与端到端耗时（每组参数重复 REPS 次取中位数）。
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agentflow.checkpoint import SQLiteCheckpointStore, new_run_id
from agentflow.state import StateGraph, StateGraphError

WORK_SECONDS = 0.05  # 单节点模拟开销
REPS = 3  # 每组参数重复次数（取中位数）


def make_node_fn(i: int, inject: dict[int, bool]):
    async def _node(state: dict) -> dict:
        if inject.get(i):
            raise RuntimeError(f"injected failure at node_{i}")
        await asyncio.sleep(WORK_SECONDS)
        return {f"out_{i}": i}

    return _node


def _bind(n: int, fail_index: int, inject: dict[int, bool]) -> StateGraph:
    """构造 node_0..node_{n-1} 的线性流水线，第 fail_index 个节点可注入失败。"""
    g = StateGraph(f"bench_{n}")
    for i in range(n):
        g.add_node(f"node_{i}", make_node_fn(i, inject))
    for i in range(n - 1):
        g.add_edge(f"node_{i}", f"node_{i + 1}")
    return g


def make_node_fn(i: int, inject: dict[int, bool]):
    async def _node(state: dict) -> dict:
        if inject.get(i):
            raise RuntimeError(f"injected failure at node_{i}")
        await asyncio.sleep(WORK_SECONDS)
        return {f"out_{i}": i}

    return _node


async def run_once(tmp: str, n: int, fail_index: int) -> dict:
    """单次测量：失败首跑 → 全量重跑 → resume，返回三种路径的指标。"""
    inject: dict[int, bool] = {fail_index: True}

    # 1) 首跑：在 fail_index 处失败，checkpoint 留下前缀成功记录
    store = SQLiteCheckpointStore(str(Path(tmp) / "cp.db"))
    await store.connect()
    g1 = _bind(n, fail_index, inject)
    run_id = new_run_id()
    t0 = time.perf_counter()
    try:
        await g1.run({}, checkpoint=store, run_id=run_id)
        raise AssertionError("首跑应当失败")
    except StateGraphError:
        pass
    failed_run_s = time.perf_counter() - t0
    inject[fail_index] = False  # 后续不再注入

    # 2) 全量重跑：全新 run_id + 空存储（等价无 checkpoint 的重试方式）
    g2 = _bind(n, fail_index, inject)
    t0 = time.perf_counter()
    full_state = await g2.run({}, checkpoint=store, run_id=new_run_id())
    full_s = time.perf_counter() - t0
    full_nodes = full_state["_executed_nodes"]

    # 3) resume：同 run_id，仅重跑失败节点及其后继
    g3 = _bind(n, fail_index, inject)
    t0 = time.perf_counter()
    resume_state = await g3.run({}, checkpoint=store, run_id=run_id, resume=True)
    resume_s = time.perf_counter() - t0
    resume_nodes = resume_state["_executed_nodes"]

    # 语义正确性断言：resume 恰好执行失败节点及其后继；结果与全量重跑一致
    expected = sorted(f"node_{i}" for i in range(fail_index, n))
    assert resume_nodes == expected, f"resume 执行集合不符: {resume_nodes}"
    assert len(full_nodes) == n
    assert all(resume_state.get(f"out_{i}") == i for i in range(n)), "resume 最终状态不完整"
    assert all(full_state.get(f"out_{i}") == i for i in range(n)), "全量重跑最终状态不完整"

    await store.close()
    return {
        "failed_run_s": failed_run_s,
        "full_s": full_s,
        "resume_s": resume_s,
        "full_count": len(full_nodes),
        "resume_count": len(resume_nodes),
    }


async def bench(n: int, fail_index: int) -> dict:
    results = []
    for _ in range(REPS):
        with tempfile.TemporaryDirectory() as tmp:
            results.append(await run_once(tmp, n, fail_index))
    med = {k: statistics.median(r[k] for r in results) for k in results[0]}
    return med


async def main() -> None:
    parser = argparse.ArgumentParser(description="StateGraph resume 基准")
    parser.add_argument(
        "--configs",
        default="5:2,10:5,20:10",
        help="逗号分隔的 N:k 列表（N 节点，第 k 个节点失败），默认 5:2,10:5,20:10",
    )
    args = parser.parse_args()

    print(f"单节点开销 {WORK_SECONDS*1000:.0f}ms，每组重复 {REPS} 次取中位数\n")

    rows = []
    for item in args.configs.split(","):
        n_s, k_s = item.split(":")
        n, k = int(n_s), int(k_s)
        m = await bench(n, k)
        node_saved = 1 - m["resume_count"] / m["full_count"]
        time_saved = 1 - m["resume_s"] / m["full_s"]
        rows.append((n, k, m, node_saved, time_saved))
        print(
            f"N={n:>2} k={k:>2} | 全量重跑 {m['full_count']:>2} 节点 {m['full_s']*1000:7.1f}ms"
            f" | resume {m['resume_count']:>2} 节点 {m['resume_s']*1000:7.1f}ms"
            f" | 节点省 {node_saved:5.1%} | 时间省 {time_saved:5.1%}"
        )

    print("\n| N | 失败位置 k | 全量重跑节点 | 全量重跑耗时 | resume 节点 | resume 耗时 | 节点节省 | 时间节省 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for n, k, m, ns, ts in rows:
        print(
            f"| {n} | {k} | {m['full_count']} | {m['full_s']*1000:.1f}ms "
            f"| {m['resume_count']} | {m['resume_s']*1000:.1f}ms | {ns:.1%} | {ts:.1%} |"
        )


if __name__ == "__main__":
    asyncio.run(main())
