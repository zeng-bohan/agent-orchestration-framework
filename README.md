# agentflow — 轻量 Agent 编排框架

从多智能体项目中沉淀出的轻量 Agent 编排框架：**DAG 图编排 + StateGraph 状态机 + SQLite Checkpoint 持久化 + MCP 工具生态**。

> 技术栈：Python 3.11+、asyncio、SQLite、MCP（stdio / SSE）、pytest
> 核心模块测试覆盖率 **89%**，Mock LLM 调用成功率 100%

## 特性

| 能力 | 说明 |
|------|------|
| 🕸️ DAG 图编排 | 拓扑分层、**节点级并行调度**（asyncio.gather）、环检测 |
| 🛣️ 条件边路由 | 条件函数决定下一节点，支持分支流程 |
| 💾 Checkpoint 持久化 | SQLite 存储节点结果，**断点续传 / 失败重试 / 幂等执行** |
| 🧩 MCP 工具生态 | 工具注册中心（**热插拔 + 版本管理**），stdio / SSE Transport |
| 📂 Skills 动态发现 | 扫描目录 `SKILL.md` 自动注册为 Skill 工具 |
| 🧪 测试工程 | Mock LLM 替代真实模型，覆盖率 80%+，调用成功率 95%+ |

## 安装

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## 快速开始

### 1) DAG 图编排（并行调度）

```python
import asyncio
from agentflow import Graph, Node

async def fetch(state):
    return {"data": ["帖子A", "帖子B", "帖子C"]}

async def analyze(state):
    return {"analysis": f"分析了 {len(state['data'])} 条数据"}

async def summarize(state):
    return {"summary": f"{state['analysis']}；共 {len(state['data'])} 条"}

async def main():
    g = Graph("舆情分析")
    g.add_node(Node("fetch", fetch))
    g.add_node(Node("analyze", analyze))
    g.add_node(Node("summarize", summarize))
    g.add_edge("fetch", "analyze")
    g.add_edge("fetch", "summarize")   # 同层并行
    state = await g.run({})
    print(state)

asyncio.run(main())
```

### 2) StateGraph 状态机 + 条件路由 + Checkpoint

```python
import asyncio
from agentflow import SQLiteCheckpointStore, StateGraph

async def crawl(state):
    return {"pages": 10}

async def positive_report(state):
    return {"report": f"正面报告（{state['pages']} 页）"}

async def negative_report(state):
    return {"report": f"负面报告（{state['pages']} 页）"}

async def route(state):
    return state.get("mood", "positive") == "positive"

async def main():
    store = SQLiteCheckpointStore("demo.db")
    g = StateGraph("报告生成")
    g.add_node("crawl", crawl)
    g.add_node("positive", positive_report)
    g.add_node("negative", negative_report)
    g.add_edge("crawl", "positive", condition=route)
    g.add_edge("crawl", "negative")

    state = await g.run({"mood": "negative"}, checkpoint=store, run_id="run-demo-1")
    print(state["report"])
    # 断点续传：再次运行同 run_id，已成功节点跳过（幂等）
    state2 = await g.run({"mood": "negative"}, checkpoint=store, run_id="run-demo-1")
    print("幂等验证:", state2 == state)

asyncio.run(main())
```

### 3) MCP 工具注册中心（热插拔 + 版本管理）

```python
import asyncio
from agentflow import MCPServer, Tool, ToolRegistry

async def add(a: int = 0, b: int = 0) -> int:
    """加法。"""
    return a + b

async def main():
    reg = ToolRegistry()
    reg.register(Tool(name="add", description="加法", parameters={
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
    }, fn=add))

    server = MCPServer(reg)
    resp = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    print("tools:", resp["result"]["tools"])
    resp = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                "params": {"name": "add", "arguments": {"a": 1, "b": 2}}})
    print("call:", resp["result"]["content"][0]["text"])

    # 热更新 + 版本回滚
    reg.update("add", Tool(name="add", description="加法v2", parameters={}, fn=lambda **k: 0))
    print("版本历史:", reg.versions("add"))
    reg.rollback("add")

asyncio.run(main())
```

### 4) Skills 动态发现

```python
from agentflow import ToolRegistry

reg = ToolRegistry()
n = reg.discover_skills("./skills")   # 扫描 skills/**/SKILL.md
print(f"发现 {n} 个 Skill 工具:", reg.names())
```

## 架构

```
┌─────────────────────────────────────────────────────┐
│                    agentflow                        │
│                                                     │
│  Graph ──拓扑分层──► 节点级并行调度 ──► 条件边路由     │
│    │                                                │
│    └──► StateGraph ──► SQLite Checkpoint ──► 断点续传│
│                              │  失败重试 / 幂等      │
│                                                     │
│  MCP ──► ToolRegistry（热插拔 / 版本管理）            │
│    │       ├─ StdioTransport                        │
│    │       └─ SSETransport                          │
│    └──► Skills 动态发现（SKILL.md）                  │
│                                                     │
│  LLM 抽象 ──► MockLLM（离线/测试） / 真实模型         │
└─────────────────────────────────────────────────────┘
```

## 测试

```bash
.venv/Scripts/python -m pytest tests -q
.venv/Scripts/python -m pytest tests -q --cov=agentflow --cov-report=term
```

## 与 LangGraph 对比

见 [docs/langgraph-comparison.md](docs/langgraph-comparison.md)。

## 目录结构

```
agentflow/
├── graph.py         # DAG 图编排（并行分层、条件边、环检测）
├── state.py         # StateGraph 状态机（断点续传、失败重试、幂等）
├── checkpoint.py    # SQLite checkpoint 存储
├── executor.py      # 统一执行入口
├── llm.py           # LLM 抽象 + MockLLM
└── mcp/
    ├── registry.py  # 工具注册中心（热插拔 / 版本管理 / Skills 发现）
    └── transport.py # stdio / SSE Transport
```

## 许可

Apache 2.0
