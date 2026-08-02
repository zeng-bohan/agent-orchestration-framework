"""Checkpoint 持久化：SQLite 存储，支持断点续传 / 失败重试 / 幂等执行。

- 每次节点执行后写入 checkpoint（状态快照 + 节点结果）；
- 断点续传：resume 时跳过已成功节点，从失败/未执行节点继续；
- 幂等执行：同一 checkpoint 下节点执行具有确定性（已成功节点不重复执行）。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import aiosqlite


class CheckpointStore:
    """Checkpoint 存储抽象接口。"""

    async def save(self, run_id: str, node: str, status: str, state: dict, error: str | None = None) -> None:
        raise NotImplementedError

    async def load(self, run_id: str) -> dict[str, Any]:
        """返回 {node: {status, state, error, ts}, ...}。"""
        raise NotImplementedError

    async def nodes(self, run_id: str) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    async def delete(self, run_id: str) -> None:
        raise NotImplementedError


class SQLiteCheckpointStore(CheckpointStore):
    """基于 SQLite 的 checkpoint 存储（aiosqlite）。"""

    def __init__(self, path: str = "agentflow.db") -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                run_id TEXT NOT NULL,
                node TEXT NOT NULL,
                status TEXT NOT NULL,
                state TEXT NOT NULL,
                error TEXT,
                ts REAL NOT NULL,
                PRIMARY KEY (run_id, node)
            )
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def save(
        self, run_id: str, node: str, status: str, state: dict, error: str | None = None
    ) -> None:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        await self._conn.execute(
            """
            INSERT INTO checkpoints (run_id, node, status, state, error, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, node) DO UPDATE SET
                status = excluded.status,
                state = excluded.state,
                error = excluded.error,
                ts = excluded.ts
            """,
            (run_id, node, status, json.dumps(state, ensure_ascii=False), error, time.time()),
        )
        await self._conn.commit()

    async def nodes(self, run_id: str) -> dict[str, dict[str, Any]]:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        cur = await self._conn.execute(
            "SELECT node, status, state, error, ts FROM checkpoints WHERE run_id = ?",
            (run_id,),
        )
        rows = await cur.fetchall()
        return {
            node: {"status": status, "state": json.loads(state), "error": error, "ts": ts}
            for node, status, state, error, ts in rows
        }

    async def load(self, run_id: str) -> dict[str, Any]:
        nodes = await self.nodes(run_id)
        # 状态合并：所有已成功节点的 state 增量（后写覆盖）
        merged: dict[str, Any] = {}
        for meta in nodes.values():
            if meta["status"] == "succeeded":
                merged.update(meta["state"])
        return merged

    async def delete(self, run_id: str) -> None:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        await self._conn.execute("DELETE FROM checkpoints WHERE run_id = ?", (run_id,))
        await self._conn.commit()


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"
