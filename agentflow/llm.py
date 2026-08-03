"""LLM 抽象：Agent 节点的统一 LLM 接口 + MockLLM（测试/离线确定性实现）。"""
from __future__ import annotations

from typing import Any, Awaitable, Callable


class BaseLLM:
    """LLM 接口：接收消息列表与工具，返回文本。"""

    name: str = "base"

    async def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> str:
        raise NotImplementedError


class MockLLM(BaseLLM):
    """确定性 Mock：基于规则返回文本，便于单元测试与评测。

    - 若传入工具，返回「将使用工具 X」的固定文本（可配置）；
    - 默认根据最后一条用户消息生成可预测的分析文本。
    """

    name = "mock"

    def __init__(self, reply_template: str | None = None) -> None:
        self._template = reply_template or "【Mock 回复】已处理请求：{query}"
        self.calls: list[dict[str, Any]] = []

    async def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> str:
        self.calls.append({"messages": list(messages), "tools": tools})
        query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                query = str(m.get("content", ""))
                break
        if tools:
            names = [t.get("name", "?") for t in tools]
            return f"【Mock 回复】将依次调用工具: {', '.join(names)}"
        return self._template.format(query=query or "（空）")


LLMFn = Callable[[list[dict[str, Any]]], Awaitable[str]]
