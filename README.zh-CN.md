<p align="center">
  <img src="docs/banner.svg" width="800" alt="agentflow" />
</p>

<h1 align="center">agentflow</h1>

<p align="center">
  轻量级 Python 智能体工作流编排框架：DAG 调度、有状态恢复、MCP 工具与技能发现。
</p>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
[![CI](https://github.com/zeng-bohan/agent-orchestration-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/zeng-bohan/agent-orchestration-framework/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/License-Apache--2.0-4EB1BA?style=flat-square)

## 核心特性

- **DAG 编排**：拓扑分层、环检测，基于 `asyncio.gather` 的并行节点执行。
- **StateGraph**：条件路由 + SQLite 检查点，支持断点续跑、重试与幂等执行。
- **MCP 工具**：带版本管理的工具注册表，支持 stdio 与 SSE 两种传输。
- **技能发现**：扫描 `SKILL.md` 文件并注册为工具。
- **可测试设计**：离线 `MockLLM` 支持；实测版本 44 个测试全过，核心模块覆盖率 89%。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 语言与运行时 | Python 3.11+、`asyncio` |
| 编排 | DAG 调度器（拓扑分层、并行执行）+ 有状态 StateGraph |
| 状态与恢复 | SQLite 检查点存储，逐节点执行记录 |
| 工具协议 | MCP 工具注册表，stdio 与 SSE 传输 |
| 技能发现 | `SKILL.md` 扫描 → 工具注册 |
| 测试 | pytest + 离线 `MockLLM` |
| 打包 | `pyproject.toml`（发行名 `agentflow-lite`，导入名 `agentflow`） |

## 安装

```bash
# Windows
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# macOS / Linux
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

或以包形式安装：`pip install -e .`（发行名 `agentflow-lite`，导入名 `agentflow`）。

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

## 演示：故障后恢复

`examples/` 里有两个可运行示例：

```bash
python examples/quickstart.py            # DAG 流水线 + 条件路由 + 检查点恢复 + MCP 工具
python examples/resume_after_failure.py  # 流水线中途失败后恢复：只重跑失败的节点
```

`resume_after_failure.py` 演示核心生产语义：首次运行时 `publish` 在 `crawl`/`transform` 成功之后失败；用同一个 `run_id` 重跑会输出 `_executed_nodes: ['publish']` — 已成功的节点从检查点恢复，不重复计算。

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
examples/            # quickstart 与 resume-after-failure 演示
tests/               # graph、state、executor 与 MCP 测试
pyproject.toml       # 打包元数据
```

状态管理与检查点设计的取舍，见[与 LangGraph 的对比](docs/langgraph-comparison.md)。

## 注意事项与避坑

- **检查点语义是设计选择，不是 bug。** 用同一个 `run_id` 重跑只会执行检查点里缺失的节点；已成功的节点原样恢复。如果两次运行之间改了图拓扑，请换一个新的 `run_id`。
- **默认完全离线。** 未配置 API key 时 `MockLLM` 顶替 LLM，整个测试套件和示例都不需要网络与模型下载。
- **命名。** PyPI 发行名是 `agentflow-lite`（裸 `agentflow` 已被占用）；导入名保持 `agentflow`。
- **Windows 路径。** venv 解释器在 Windows 上是 `.venv\Scripts\python`，其他平台是 `.venv/bin/python` — 上面的片段两种都给了。
- **刻意留白。** 人在环路中断、节点事件流、注解 reducer、非 SQLite 检查点后端都在路线图上，不是遗漏 — 见[路线图](#路线图)。

## 路线图

刻意未实现的 LangGraph 对齐能力，按优先级：人在环路中断（暂停执行等待批准）、节点执行事件流、并行分支状态合并的注解 reducer、SQLite 之外的 Postgres/Redis 检查点后端。

## 支持

Bug、问题与功能建议：[提 Issue](https://github.com/zeng-bohan/agent-orchestration-framework/issues)。Bug 报告请附复现步骤与相关日志或输出。

## 贡献

个人维护项目。欢迎提 Issue 反馈 Bug 与想法；代码改动请先开 Issue 对齐方案，再投入时间。

## 许可证

[Apache License 2.0](LICENSE)
