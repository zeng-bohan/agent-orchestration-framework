"""失败后断点续传：已成功节点不重算，只重做失败节点。

场景：三步流水线 crawl → transform → publish。第一次运行时 publish 因「下游服务
不可用」失败；排障后用同一 run_id 重跑——crawl / transform 从 checkpoint 恢复直接
跳过，只有 publish 真正重执行。长任务生产调度的核心语义：失败重试的代价 = 失败
节点本身，而不是整条流水线。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentflow import StateGraph, SQLiteCheckpointStore

PUBLISH_AVAILABLE = False  # 模拟下游服务状态：第一次运行为不可用


async def crawl(state):
    return {"pages": 10}


async def transform(state):
    return {"items": state["pages"] * 8}


async def publish(state):
    if not PUBLISH_AVAILABLE:
        raise RuntimeError("下游服务 503")
    return {"published": state["items"]}


async def main() -> None:
    store = SQLiteCheckpointStore("resume_demo.db")
    sg = (
        StateGraph("发布流水线")
        .add_node("crawl", crawl)
        .add_node("transform", transform)
        .add_node("publish", publish)
        .add_edge("crawl", "transform")
        .add_edge("transform", "publish")
    )

    print("=== 第一次运行：publish 失败，前序节点已落 checkpoint ===")
    try:
        await sg.run({}, checkpoint=store, run_id="run-resume-demo")
    except Exception as exc:
        print(f"按预期失败: {exc}")
    statuses = {n: m["status"] for n, m in (await store.nodes("run-resume-demo")).items()}
    print("checkpoint 状态:", statuses)

    print("\n=== 下游恢复后，同一 run_id 重跑 ===")
    global PUBLISH_AVAILABLE
    PUBLISH_AVAILABLE = True
    state = await sg.run({}, checkpoint=store, run_id="run-resume-demo")
    print("最终结果:", {k: state[k] for k in ("pages", "items", "published")})
    print("实际执行的节点:", state["_executed_nodes"], "← 只有失败节点被重做")


if __name__ == "__main__":
    asyncio.run(main())
