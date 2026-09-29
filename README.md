<p align="center">
  <img src="docs/banner.svg" width="800" alt="agentflow" />
</p>

# agentflow

> English | [简体中文](README.zh-CN.md)

A lightweight Python framework for orchestrating agent workflows with DAG scheduling, stateful recovery, MCP tools, and skill discovery.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache--2.0-4EB1BA?style=flat-square)
[![CI](https://github.com/zeng-bohan/agent-orchestration-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/zeng-bohan/agent-orchestration-framework/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-44%20passing%20%2F%2089%25%20coverage-2EA043?style=flat-square)

## Highlights

- **DAG orchestration**: topological layering, cycle detection, and parallel node execution with `asyncio.gather`.
- **StateGraph**: conditional routing plus SQLite checkpoints for resume, retry, and idempotent execution.
- **MCP tools**: a versioned tool registry with stdio and SSE transports.
- **Skill discovery**: scans `SKILL.md` files and registers them as tools.
- **Testable design**: offline `MockLLM` support; 44 tests passed and 89% core-module coverage at the measured revision.

## Install

```bash
# Windows
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# macOS / Linux
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Or install as a package: `pip install -e .` (distribution name `agentflow-lite`, import name `agentflow`).

## Quick start

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

For resumable execution, pass a `SQLiteCheckpointStore` and a stable `run_id` to `StateGraph.run`.

## Examples

Two runnable examples live in `examples/`:

```bash
python examples/quickstart.py            # DAG pipeline + conditional routing + checkpoint resume + MCP tools
python examples/resume_after_failure.py  # failure mid-pipeline, then resume: only the failed node re-runs
```

`resume_after_failure.py` demonstrates the core production semantics: on the first run `publish` fails after `crawl`/`transform` succeeded; re-running with the same `run_id` reports `_executed_nodes: ['publish']` — the succeeded nodes are restored from the checkpoint and are not recomputed.

## Test

```bash
# Windows
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python -m pytest tests -q --cov=agentflow --cov-report=term

# macOS / Linux
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests -q --cov=agentflow --cov-report=term
```

## Project structure

```text
agentflow/
├── graph.py         # DAG scheduling and conditional edges
├── state.py         # StateGraph workflow
├── checkpoint.py    # SQLite checkpoint storage
├── executor.py      # unified execution entry point
├── llm.py           # LLM abstraction and MockLLM
└── mcp/
    ├── registry.py  # tool registry and skill discovery
    └── transport.py # stdio and SSE transports
examples/            # quickstart and resume-after-failure demos
tests/               # graph, state, executor, and MCP tests
pyproject.toml       # packaging metadata
```

See [the comparison with LangGraph](docs/langgraph-comparison.md) for the state-management and checkpoint design trade-offs.

## Roadmap

LangGraph-parity capabilities deliberately left out, in priority order: human-in-the-loop interrupts (pause a run awaiting approval), streaming node execution events, annotated reducers for parallel-branch state merging, and Postgres/Redis checkpoint backends beyond SQLite.

## Support

Bugs, questions, and feature ideas: [open an issue](https://github.com/zeng-bohan/agent-orchestration-framework/issues). Bug reports should include reproduction steps and the relevant logs or output.

## Contributing

This is a solo-maintained project. Issues for bugs and ideas are very welcome; for code changes, please open an issue first so the approach can be discussed before you invest time.

## License

[Apache License 2.0](LICENSE)
