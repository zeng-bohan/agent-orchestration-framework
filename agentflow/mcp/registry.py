"""MCP 兼容工具注册中心。

- 工具注册：名称 / 描述 / 参数 JSON Schema / 异步执行函数 / 版本；
- 热插拔：运行时 register / unregister / update，实时生效；
- 版本管理：同名单工具保留历史版本，可回滚（rollback）；
- Skills 动态发现：扫描目录中的 SKILL.md，注册为 Skill 工具；
- 协议：tools/list / tools/call（与 MCP 标准对齐），供 stdio / SSE Transport 复用。
"""
from __future__ import annotations

import importlib.util
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

# 工具执行函数：async (**kwargs) -> Any
ToolFn = Callable[..., Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_schema(self) -> dict[str, Any]:
        """MCP tools/list 规范格式。"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            },
        }


class ToolRegistryError(RuntimeError):
    pass


class ToolRegistry:
    """工具注册中心：热插拔 + 版本管理。"""

    def __init__(self) -> None:
        # name -> {version: Tool}
        self._versions: dict[str, dict[str, Tool]] = {}
        # name -> 当前生效版本
        self._active: dict[str, str] = {}
        # name -> 历史版本列表（降序）
        self._history: dict[str, list[str]] = {}

    # ---------- 注册 / 注销（热插拔） ----------

    def register(self, tool: Tool) -> None:
        """注册工具。同名单时按版本号升版本（热更新）。"""
        if tool.name in self._active:
            old = self._active[tool.name]
            new_ver = self._bump(old, tool.version)
        else:
            new_ver = tool.version
        tool.version = new_ver
        self._versions.setdefault(tool.name, {})[new_ver] = tool
        self._active[tool.name] = new_ver
        self._history.setdefault(tool.name, []).insert(0, new_ver)

    def unregister(self, name: str) -> None:
        """注销工具（热拔插）。"""
        if name not in self._active:
            raise ToolRegistryError(f"工具不存在: {name}")
        del self._active[name]
        del self._history[name]

    def update(self, name: str, tool: Tool) -> None:
        """热更新：以新版本覆盖。"""
        tool.name = name
        self.register(tool)

    def rollback(self, name: str) -> Tool | None:
        """版本回滚：回到上一个版本。"""
        history = self._history.get(name)
        if not history or len(history) < 2:
            return None
        prev = history[1]
        self._active[name] = prev
        return self._versions[name][prev]

    # ---------- 查询 ----------

    def get(self, name: str) -> Tool | None:
        ver = self._active.get(name)
        if ver is None:
            return None
        return self._versions[name][ver]

    def list(self) -> list[Tool]:
        out = []
        for name, ver in self._active.items():
            tool = self._versions[name][ver]
            out.append(tool)
        return sorted(out, key=lambda t: t.name)

    def list_schemas(self) -> list[dict[str, Any]]:
        """MCP tools/list 结果。"""
        return [t.to_schema() for t in self.list()]

    def versions(self, name: str) -> list[str]:
        return list(self._history.get(name, []))

    def names(self) -> list[str]:
        return sorted(self._active)

    def __len__(self) -> int:
        return len(self._active)

    @staticmethod
    def _bump(old: str, new: str) -> str:
        """版本号递增：显式版本号优先，否则 minor+1。"""
        if new and new != old:
            return new
        parts = [int(p) for p in old.split(".")] if old else [1, 0, 0]
        while len(parts) < 3:
            parts.append(0)
        parts[1] += 1
        return ".".join(str(p) for p in parts)

    # ---------- 调用 ----------

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """MCP tools/call：执行工具。"""
        tool = self.get(name)
        if tool is None:
            raise ToolRegistryError(f"工具不存在: {name}")
        return await tool.fn(**(arguments or {}))

    # ---------- Skills 动态发现 ----------

    def discover_skills(self, skills_dir: str | Path) -> int:
        """扫描目录中的 SKILL.md，动态注册为 Skill 工具。

        SKILL.md 格式：frontmatter（name / description）+ 正文指令。
        """
        base = Path(skills_dir)
        if not base.is_dir():
            return 0
        count = 0
        for md in sorted(base.rglob("*.md")):
            content = md.read_text(encoding="utf-8", errors="replace")
            name = self._parse_skill_name(md, content)
            if not name:
                continue
            tool = Tool(
                name=f"skill_{name}",
                description=self._parse_skill_desc(content) or f"Skill: {name}",
                parameters={"type": "object", "properties": {}, "required": []},
                fn=self._make_skill_fn(md, content),
                version="1.0.0",
                metadata={"source": str(md)},
            )
            self.register(tool)
            count += 1
        return count

    @staticmethod
    def _parse_skill_name(md: Path, content: str) -> str:
        import re

        m = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
        if m:
            return m.group(1).strip().strip('"\'')
        # 兜底：文件名（去掉 .md，目录名作为 skill 名）
        parts = md.parts
        if len(parts) >= 2 and parts[-2] == "skills":
            return parts[-1]
        return md.stem

    @staticmethod
    def _parse_skill_desc(content: str) -> str:
        import re

        m = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else ""

    @staticmethod
    def _make_skill_fn(md: Path, content: str) -> ToolFn:
        """Skill 工具执行函数：返回指令内容与文件路径。"""

        async def _skill_fn(**kwargs: Any) -> dict[str, Any]:
            return {
                "skill": md.stem,
                "source": str(md),
                "instructions": content[:4000],
                "args": kwargs,
            }

        return _skill_fn


def load_python_tools(module_path: str | Path) -> list[Tool]:
    """从 Python 文件/模块动态加载工具（供 Skills 热插拔使用）。

    模块内所有以 tool_ 开头、带 __tool__ 描述的 async 函数注册为工具。
    """
    import importlib

    path = Path(module_path)
    if path.suffix == ".py":
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(module_path)

    tools: list[Tool] = []
    for name, obj in inspect.getmembers(mod, inspect.iscoroutinefunction):
        if name.startswith("tool_"):
            tool_name = name[5:].replace("_", "-")
            doc = inspect.getdoc(obj) or f"工具 {tool_name}"
            sig = inspect.signature(obj)
            props = {p: {"type": "string"} for p in sig.parameters}
            tools.append(
                Tool(
                    name=tool_name,
                    description=doc,
                    parameters={"type": "object", "properties": props, "required": []},
                    fn=obj,
                )
            )
    return tools
