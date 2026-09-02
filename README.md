# agentflow

A lightweight Python framework for orchestrating agent workflows with DAG scheduling, stateful recovery, MCP tools, and skill discovery.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-44%20passed-4C9F70?style=flat-square)
![Coverage](https://img.shields.io/badge/Core%20coverage-89%25-4C9F70?style=flat-square)
![License](https://img.shields.io/badge/License-Apache--2.0-4EB1BA?style=flat-square)
[![CI](https://github.com/zengbohan1/agent-orchestration-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/zengbohan1/agent-orchestration-framework/actions/workflows/ci.yml)

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

Or install as a package: `pip install -e .` (see `pyproject.toml`).

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

See [the comparison with LangGraph](docs/langgraph-comparison.md).

## License

[Apache License 2.0](LICENSE)
