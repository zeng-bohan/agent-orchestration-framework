"""快速开始示例：DAG 并行 + StateGraph 条件路由 + Checkpoint 断点续传 + MCP 工具。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentflow import (
    Graph,
    MCPServer,
    Node,
    SQLiteCheckpointStore,
    StateGraph,
    Tool,
    ToolRegistry,
)


async def fetch(state):
    return {"data": ["帖子A", "帖子B", "帖子C"]}


async def analyze(state):
    return {"analysis": f"分析了 {len(state['data'])} 条数据"}


async def summarize(state):
    return {"summary": f"{state['analysis']}；共 {len(state['data'])} 条"}


async def crawl(state):
    return {"pages": 10}


async def positive_report(state):
    return {"report": f"正面报告（{state['pages']} 页）"}


async def negative_report(state):
    return {"report": f"负面报告（{state['pages']} 页）"}


async def route(state):
    return state.get("mood", "positive") == "positive"


async def tool_add(a: int = 0, b: int = 0) -> int:
    """加法工具。"""
    return a + b


async def main() -> None:
    print("=== 1) DAG 图编排（fetch → analyze → summarize 串行流水线）===")
    g = Graph("舆情分析")
    g.add_node(Node("fetch", fetch))
    g.add_node(Node("analyze", analyze))
    g.add_node(Node("summarize", summarize))
    g.add_edge("fetch", "analyze")
    g.add_edge("analyze", "summarize")
    print(await g.run({}))

    print("\n=== 2) StateGraph + 条件路由 + Checkpoint ===")
    store = SQLiteCheckpointStore("demo.db")
    sg = StateGraph("报告生成")
    sg.add_node("crawl", crawl)
    sg.add_node("positive", positive_report)
    sg.add_node("negative", negative_report)
    sg.add_edge("crawl", "positive", condition=route)
    sg.add_edge("crawl", "negative")

    state = await sg.run({"mood": "negative"}, checkpoint=store, run_id="run-demo-1")
    print("首次执行:", state["report"], "| 执行节点:", state["_executed_nodes"])
    state2 = await sg.run({"mood": "negative"}, checkpoint=store, run_id="run-demo-1")
    print("断点续传:", state2["report"], "| 幂等执行节点:", state2["_executed_nodes"])

    print("\n=== 3) MCP 工具注册中心（stdio/SSE 就绪）===")
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="add",
            description="加法",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
            fn=tool_add,
        )
    )
    server = MCPServer(reg)
    resp = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    print("tools/list:", resp["result"]["tools"])
    resp = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "add", "arguments": {"a": 1, "b": 2}},
        }
    )
    print("tools/call:", resp["result"]["content"][0]["text"])


if __name__ == "__main__":
    asyncio.run(main())
