"""
轻量 Trace(可观测性)。

  - 默认行为:把每一步事件追加到 traces/<session_id>.jsonl,无需任何配置。
  - 进阶行为:如果 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 设置好了,
              额外把同样的事件发到 Langfuse(云或自托管),用于 web UI 可视化。

事件 schema:
  { "ts": ..., "session_id": ..., "step": ..., "event": "llm_call"|"tool_call"|"final",
    "data": {...} }
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


class Tracer:
    def __init__(self, session_id: str | None = None, dir_path: str = "traces"):
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.dir = Path(dir_path)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{self.session_id}.jsonl"
        # lazy: 第一次 _write 时才真正打开文件,避免空文件残留
        self._fp = None
        self._t0 = time.time()

        # Actor stack:用于在 multi-agent 系统中标记每个事件来自哪个角色
        # (outer / supervisor / worker-WebWorker / synthesizer 等)
        self._actor_stack: list[str] = []

        # Langfuse 是否可用
        self._lf = None
        self._lf_trace = None
        self._init_langfuse()

    # ------------------------------------------------------------------
    # Actor stack:由 agent.py / agent_multi.py 在进入/退出各角色时调用
    # ------------------------------------------------------------------

    def push_actor(self, name: str) -> None:
        self._actor_stack.append(name)

    def pop_actor(self) -> None:
        if self._actor_stack:
            self._actor_stack.pop()

    def current_actor(self) -> str | None:
        return self._actor_stack[-1] if self._actor_stack else None

    def _ensure_fp(self):
        if self._fp is None:
            self._fp = self.path.open("a", encoding="utf-8")
        return self._fp

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def log_run_start(self, user_input: str) -> None:
        self._t0 = time.time()
        self._write(event="run_start", data={"user_input": user_input})
        if self._lf is not None:
            try:
                self._lf_trace = self._lf.trace(
                    name="agent.run",
                    session_id=self.session_id,
                    input=user_input,
                )
            except Exception:
                self._lf_trace = None

    def log_llm_call(
        self,
        step: int,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency: float,
        thought: str | None,
    ) -> None:
        self._write(
            event="llm_call",
            data={
                "step": step,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "latency_s": round(latency, 4),
                "thought": thought,
            },
        )
        if self._lf_trace is not None:
            try:
                self._lf_trace.generation(
                    name=f"step-{step}-llm",
                    model=model,
                    output=thought,
                    usage={
                        "input": prompt_tokens,
                        "output": completion_tokens,
                        "total": total_tokens,
                    },
                    metadata={"latency_s": latency},
                )
            except Exception:
                pass

    def log_tool_call(
        self,
        step: int,
        name: str,
        arguments: dict | str,
        result: str,
        latency: float,
        is_error: bool = False,
    ) -> None:
        self._write(
            event="tool_call",
            data={
                "step": step,
                "name": name,
                "arguments": arguments,
                "result_preview": result[:500],
                "latency_s": round(latency, 4),
                "is_error": is_error,
            },
        )
        if self._lf_trace is not None:
            try:
                self._lf_trace.span(
                    name=f"step-{step}-{name}",
                    input=arguments,
                    output=result[:2000],
                    metadata={"latency_s": latency, "is_error": is_error},
                )
            except Exception:
                pass

    def log_run_end(
        self,
        final_answer: str,
        total_tokens: int,
        elapsed: float,
    ) -> None:
        self._write(
            event="run_end",
            data={
                "final_answer": final_answer[:2000],
                "total_tokens": total_tokens,
                "elapsed_s": round(elapsed, 4),
            },
        )
        if self._lf_trace is not None:
            try:
                self._lf_trace.update(output=final_answer)
            except Exception:
                pass

    def log(self, event: str, data: dict[str, Any]) -> None:
        """通用日志入口,供 tracing_http / mcp_provider / 任何下游使用。"""
        self._write(event=event, data=data)

    def close(self) -> None:
        if self._fp is not None:
            try:
                self._fp.flush()
                self._fp.close()
            except Exception:
                pass
        if self._lf is not None:
            try:
                self._lf.flush()
            except Exception:
                pass

    def rotate(self, new_session_id: str) -> None:
        """切换到新的 session_id,后续事件写入新文件。

        典型场景:交互模式下每轮 chat 一个独立 trace 文件。
        如果旧文件还是空的(没写过任何事件),会被清理掉。
        Langfuse trace 也会重置(下次 log_run_start 时重建)。
        """
        old_path = self.path
        old_was_empty = self._fp is None
        if self._fp is not None:
            try:
                self._fp.flush()
                self._fp.close()
            except Exception:
                pass
        # 清理空文件
        if old_was_empty and old_path.exists() and old_path.stat().st_size == 0:
            try:
                old_path.unlink()
            except Exception:
                pass
        self.session_id = new_session_id
        self.path = self.dir / f"{new_session_id}.jsonl"
        self._fp = None  # lazy
        self._lf_trace = None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _write(self, event: str, data: dict[str, Any]) -> None:
        # 把当前 actor 自动注入 event(若调用方没显式塞过 actor 字段)
        actor = self.current_actor()
        if actor and isinstance(data, dict) and "actor" not in data:
            data = {**data, "actor": actor}
        record = {
            "ts": time.time(),
            "session_id": self.session_id,
            "event": event,
            "data": data,
        }
        fp = self._ensure_fp()
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        fp.flush()

    def _init_langfuse(self) -> None:
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        if not (public_key and secret_key):
            return
        try:
            from langfuse import Langfuse  # type: ignore

            self._lf = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
        except Exception:
            self._lf = None
