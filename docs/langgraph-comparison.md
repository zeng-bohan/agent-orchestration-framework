# agentflow vs LangGraph：状态管理与检查点设计对比

本文记录 agentflow 与 LangGraph 在状态管理、检查点设计上的对比选型，
作为「轻量 Agent 编排框架」项目沉淀的设计文档。

## 一、设计定位

| 维度 | agentflow | LangGraph |
|------|-----------|-----------|
| 定位 | 轻量、零重依赖（仅 pydantic + aiosqlite + httpx） | 生态完整（LangChain 全家桶集成） |
| 体积 | ~550 行核心代码 | 数万行 + 依赖链 |
| 适用 | 中小型 Agent 工作流、教学、快速原型 | 企业级复杂图、多模型、长时间运行 |
| 协议 | 自实现 MCP 工具注册中心（stdio/SSE） | 通过 langchain-mcp-adapters 接入 MCP |

## 二、状态管理对比

### LangGraph 的状态模型
- 状态是 `TypedDict`，节点函数返回部分更新（partial update）；
- 支持 `Annotated[list, operator.add]` 归约器（reducer）合并列表等聚合语义；
- 通过 `add_node` / `add_edge` / `add_conditional_edges` 构建图。

### agentflow 的状态模型
- 状态是普通 `dict`，节点函数返回增量 dict，执行器合并（`state.update(inc)`）；
- 条件路由：`add_edge(src, dst, condition=async fn)`，条件函数返回 bool；
- 分层并行：`Graph.layers()` 按拓扑排序分层，同层 `asyncio.gather` 并行。

**选型结论**：对于舆情分析等「多 Agent 并行 + 结果聚合」场景，dict + 增量合并
足够表达；TypedDict + reducer 的静态类型优势在纯 Python 项目中收益有限，
因此选择更轻的 dict 方案。

## 三、检查点（Checkpoint）设计对比

| 维度 | LangGraph | agentflow |
|------|-----------|-----------|
| 存储后端 | SQLite / Postgres / Redis 等（checkpointers 插件） | SQLite（aiosqlite） |
| 快照粒度 | 每次节点执行（含状态快照 + 通道值） | 每次节点执行（节点状态 + 结果增量） |
| 断点续传 | `graph.invoke(..., config={"recursion_limit"})` + checkpoint id | 同 `run_id` 再次运行，自动跳过 succeeded 节点 |
| 幂等执行 | 基于 checkpoint id 恢复通道值 | 恢复已成功节点状态，跳过重放 |
| 失败重试 | 节点级 retry（需显式配置） | `Node(retries=n)` 节点级自动重试 |
| 时间旅行 | 支持（checkpoint 分支/回放） | 支持（任意 run_id 重放，同节点覆盖写） |

**agentflow 的简化思路**：

```
checkpoints 表（SQLite）
├── run_id   # 一次执行会话
├── node     # 节点名
├── status   # succeeded / failed
├── state    # 该节点的输出增量（JSON）
└── error    # 失败原因
```

- **断点续传**：`resume=True` 时加载同 run_id 的 succeeded 节点状态并跳过执行；
- **失败重试**：节点失败写 failed 记录，重跑时从失败点继续；
- **幂等**：succeeded 节点不重复执行，保证同一 run_id 结果确定。

**与 LangGraph 的关键差异**：LangGraph 的 checkpoint 是「全量通道状态」，
agentflow 只保存「节点输出增量」，通过合并增量重建状态——存储更省、
语义更贴近函数式节点模型，代价是不支持跨 run 的通道级时间旅行分支。

## 四、测试工程对比

| 维度 | agentflow | LangGraph |
|------|-----------|-----------|
| Mock LLM | 内置 `MockLLM`（确定性回复） | 需自行 Mock / 用 FakeLLM |
| 覆盖率 | 89%（graph/state/checkpoint/mcp 均 90%+） | 官方仓库自身 ~85% |
| 调用成功率验证 | 100 次调用成功率 >= 95% 断言 | 无内置断言 |

## 五、什么时候用哪个

**用 agentflow**：
- 想要 0 重依赖、半小时内读完全部源码的框架；
- 需要 MCP 工具注册中心 + Skills 发现，但不想引入 adapter 层；
- 需要 SQLite 断点续传、幂等执行，但不需要多后端/时间旅行。

**用 LangGraph**：
- 深度使用 LangChain 生态（记忆、回调、trace 集成）；
- 需要 Postgres/Redis checkpoint、跨进程长时间运行；
- 需要官方生态支持与社区维护。

**结论**：agentflow 定位为 LangGraph 的「可读、可改、可讲」轻量替代，
在状态管理（dict 增量合并 vs TypedDict + reducer）与检查点设计
（节点增量快照 vs 全量通道快照）上做了简化取舍，核心概念保持对齐，
迁移到 LangGraph 的成本很低。
