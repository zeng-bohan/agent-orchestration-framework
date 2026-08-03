"""LLM 抽象：Agent 节点的统一 LLM 接口。"""
from __future__ import annotations

from typing import Any, Awaitable, Callable


class BaseLLM:
    """LLM 接口：接收消息列表与工具，返回文本。"""

    name: str = "base"

    async def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> str:
        raise NotImplementedError


LLMFn = Callable[[list[dict[str, Any]]], Awaitable[str]]
