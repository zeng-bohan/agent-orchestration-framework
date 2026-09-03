<p align="center">
  <img src="docs/banner.svg" width="800" alt="agentflow" />
</p>

# agentflow

> [English](README.md) | 简体中文

一个轻量级 Python 智能体工作流编排框架——DAG 调度、有状态恢复、MCP 工具、技能发现。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-44%20passed-4C9F70?style=flat-square)
![Coverage](https://img.shields.io/badge/Core%20coverage-89%25-4C9F70?style=flat-square)
![License](https://img.shields.io/badge/License-Apache--2.0-4EB1BA?style=flat-square)
[![CI](https://github.com/zengbohan1/agent-orchestration-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/zengbohan1/agent-orchestration-framework/actions/workflows/ci.yml)

## 亮点

- **DAG 编排**：拓扑分层、环检测，`asyncio.gather` 并行执行节点。
- **StateGraph**：条件路由 + SQLite 检查点，支持断点续跑、失败重试与幂等执行。
- **MCP 工具**：带版本管理的工具注册表，stdio 与 SSE 两种传输。
- **技能发现**：扫描 `SKILL.md` 文件并注册为工具。
- **可测试设计**：离线 `MockLLM` 支持；实测版本 44 个测试全通过，核心模块覆盖率 89%。

## 安装

```bash
# Windows
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# macOS / Linux
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

也可以作为包安装：`pip install -e .`（见 `pyproject.toml`）。

## 快速开始

```python
import asyncio
from agentflow import Graph, Node

async def fetch(state):
    return {"items": ["post-a", "post-b"]}

async def summarize(state):
    return {"summary": f"processed {len(state['items'])} items"}

async def main():
    graph = Graph("analysis")
    graph.add_node(Node("fetch", fetch))
    graph.add_node(Node("summarize", summarize))
    graph.add_edge("fetch", "summarize")
    print(await graph.run({}))

asyncio.run(main())
```

需要可恢复执行时，给 `StateGraph.run` 传入 `SQLiteCheckpointStore` 和稳定的 `run_id`。

## 示例

`examples/` 里有两个可直接运行的例子：

```bash
python examples/quickstart.py            # DAG 流水线 + 条件路由 + 检查点续跑 + MCP 工具
python examples/resume_after_failure.py  # 流水线中途失败后恢复：只有失败节点重跑
```

`resume_after_failure.py` 演示核心的生产语义：第一轮 `crawl`/`transform` 成功后 `publish` 失败；用同一个 `run_id` 重跑会报告 `_executed_nodes: ['publish']`——已成功的节点从检查点恢复，不重复计算。

## 测试

```bash
# Windows
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python -m pytest tests -q --cov=agentflow --cov-report=term

# macOS / Linux
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests -q --cov=agentflow --cov-report=term
```

## 项目结构

```text
agentflow/
├── graph.py         # DAG 调度与条件边
├── state.py         # StateGraph 工作流
├── checkpoint.py    # SQLite 检查点存储
├── executor.py      # 统一执行入口
├── llm.py           # LLM 抽象与 MockLLM
└── mcp/
    ├── registry.py  # 工具注册表与技能发现
    └── transport.py # stdio 与 SSE 传输
examples/            # 快速开始与失败恢复演示
tests/               # graph、state、executor、MCP 测试
pyproject.toml       # 打包元数据
```

与 LangGraph 的对比见[这篇文档](docs/langgraph-comparison.md)。

## 许可证

[Apache License 2.0](LICENSE)
