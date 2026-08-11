"""
两层记忆:

  1) SessionStore   — SQLite 持久化每次任务的 (user_input, agent_answer)
                      可按 session_id 跨次运行检索"上次任务最近聊了什么"。

  2) VectorMemory   — 用 Ollama 的 embedding 模型(默认 nomic-embed-text)做语义检索
                      不依赖外部向量库,纯 numpy + 一个 JSON 文件持久化。

设计目标:零外部服务、文件持久化、< 200 行。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np


# ---------------------------------------------------------------------------
# 1. Embedding 客户端(走 Ollama 原生接口)
# ---------------------------------------------------------------------------


class OllamaEmbedder:
    """调用 Ollama 的 /api/embeddings 拿到一段文本的向量。"""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        tracer=None,
    ):
        self.base_url = (base_url or os.getenv("EMBED_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("EMBED_MODEL", "nomic-embed-text:latest")

        if tracer is not None:
            from tracing_http import make_traced_client

            self._client = make_traced_client(tracer, timeout=30.0)
        else:
            self._client = httpx.Client(timeout=30.0)

    def embed(self, text: str) -> np.ndarray:
        resp = self._client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        resp.raise_for_status()
        data = resp.json()
        return np.asarray(data["embedding"], dtype=np.float32)

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# 2. Session(SQLite)
# ---------------------------------------------------------------------------


@dataclass
class TurnRecord:
    session_id: str
    ts: float
    user_input: str
    agent_answer: str


class SessionStore:
    """每次 agent.run() 结束后,把 (user, agent) 落 SQLite,可按 session_id 拉历史。"""

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                ts           REAL NOT NULL,
                user_input   TEXT NOT NULL,
                agent_answer TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, ts DESC)"
        )
        self._conn.commit()

    def add(self, session_id: str, user_input: str, agent_answer: str) -> None:
        self._conn.execute(
            "INSERT INTO turns(session_id, ts, user_input, agent_answer) VALUES (?, ?, ?, ?)",
            (session_id, time.time(), user_input, agent_answer),
        )
        self._conn.commit()

    def recent(self, session_id: str, limit: int = 5) -> list[TurnRecord]:
        cur = self._conn.execute(
            "SELECT session_id, ts, user_input, agent_answer "
            "FROM turns WHERE session_id = ? ORDER BY ts DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cur.fetchall()
        rows.reverse()
        return [TurnRecord(*r) for r in rows]

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# 3. VectorMemory(numpy + JSON 持久化)
# ---------------------------------------------------------------------------


class VectorMemory:
    """轻量向量记忆。所有向量都加载进内存,JSON 落盘持久化。
    适合 demo / < 10k 条记录的场景;真正生产建议换 Chroma / pgvector / Qdrant。
    """

    def __init__(self, embedder: OllamaEmbedder, path: str = "memory_vectors.json"):
        self.embedder = embedder
        self.path = Path(path)
        self.records: list[dict] = []  # {"id", "text", "metadata", "embedding": [...]}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.records = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.records = []

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, text: str, metadata: dict | None = None) -> str:
        emb = self.embedder.embed(text)
        rec_id = str(uuid.uuid4())
        self.records.append(
            {
                "id": rec_id,
                "text": text,
                "metadata": metadata or {},
                "embedding": emb.tolist(),
            }
        )
        self._save()
        return rec_id

    def search(self, query: str, k: int = 3, min_score: float = 0.3) -> list[dict]:
        if not self.records:
            return []
        q_emb = self.embedder.embed(query)
        q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)

        scored: list[tuple[float, dict]] = []
        for rec in self.records:
            v = np.asarray(rec["embedding"], dtype=np.float32)
            v_norm = v / (np.linalg.norm(v) + 1e-9)
            score = float(np.dot(q_norm, v_norm))
            if score >= min_score:
                scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"score": s, "text": r["text"], "metadata": r["metadata"]}
            for s, r in scored[:k]
        ]


# ---------------------------------------------------------------------------
# 4. Memory 整合层
# ---------------------------------------------------------------------------


class Memory:
    """对外的统一门面:agent 只跟这一个对象打交道。"""

    def __init__(
        self,
        session_id: str | None = None,
        db_path: str = "memory.db",
        vec_path: str = "memory_vectors.json",
        embedder: OllamaEmbedder | None = None,
        tracer=None,
    ):
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.session = SessionStore(db_path)
        self.embedder = embedder or OllamaEmbedder(tracer=tracer)
        self.vector = VectorMemory(self.embedder, path=vec_path)

    def build_preamble(self, user_input: str) -> str | None:
        """根据当前 user_input,构造一段可以塞到 system 后面的"上下文回忆"。"""
        parts: list[str] = []

        recent = self.session.recent(self.session_id, limit=3)
        if recent:
            block = "\n".join(
                f"- 上一轮用户:{r.user_input}\n  你回复:{r.agent_answer[:200]}"
                for r in recent
            )
            parts.append(f"## 本会话最近的对话历史\n{block}")

        hits = self.vector.search(user_input, k=3)
        if hits:
            block = "\n".join(
                f"- (相似度 {h['score']:.2f}) {h['text'][:200]}" for h in hits
            )
            parts.append(f"## 跨会话语义检索到的相关记忆\n{block}")

        if not parts:
            return None
        return "以下是与本次任务可能相关的历史信息,仅供参考:\n\n" + "\n\n".join(parts)

    def remember(self, user_input: str, agent_answer: str) -> None:
        self.session.add(self.session_id, user_input, agent_answer)
        merged = f"用户问:{user_input}\nAgent 答:{agent_answer}"
        try:
            self.vector.add(
                merged, metadata={"session_id": self.session_id, "ts": time.time()}
            )
        except Exception:
            # 嵌入服务暂时不可用时,session 仍然落了库,不阻塞主流程。
            pass

    def close(self) -> None:
        self.session.close()
        self.embedder.close()
