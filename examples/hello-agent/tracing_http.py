"""
HTTP 层 tracing。

通过 httpx 的 event hooks,我们可以**透明地**抓住:
  - OpenAI / 其他 OpenAI 兼容 API 的所有调用(因为 openai SDK 内部用 httpx)
  - Ollama embeddings(memory.py 里的 httpx.Client)
  - 任何其他走 httpx 的下游调用

记录的 event 形态:
  http_request  : { url, method, body }
  http_response : { url, status, latency_s, body }

body 会自动尝试 JSON 解析(便于查看),并按 TRACE_MAX_BODY_CHARS 截断。
"""

from __future__ import annotations

import json
import os
import time

import httpx
from openai import OpenAI


def _max_body_chars() -> int:
    try:
        return int(os.getenv("TRACE_MAX_BODY_CHARS", "4000"))
    except ValueError:
        return 4000


def _decode_body(content: bytes | None):
    """把 bytes 解成 JSON / 文本 / 占位串,并按上限截断。"""
    if not content:
        return None
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return f"(binary, {len(content)} bytes)"

    limit = _max_body_chars()
    truncated = False
    if len(text) > limit:
        text = text[:limit]
        truncated = True

    # 优先解析成 JSON,trace 文件里阅读体验更好
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text + (f"\n…(truncated, total > {limit} chars)" if truncated else "")

    if truncated and isinstance(parsed, dict):
        parsed["_truncated"] = True
    return parsed


def make_traced_client(tracer, **kwargs) -> httpx.Client:
    """返回一个 httpx.Client,所有进出流量自动写入 tracer。"""

    def request_hook(request: httpx.Request) -> None:
        request.extensions["_trace_started"] = time.perf_counter()
        tracer.log(
            "http_request",
            {
                "url": str(request.url),
                "method": request.method,
                "body": _decode_body(request.content),
            },
        )

    def response_hook(response: httpx.Response) -> None:
        try:
            if not response.is_closed:
                response.read()
            body_bytes = response.content
        except Exception:
            body_bytes = b""
        start = response.request.extensions.get("_trace_started")
        latency = time.perf_counter() - start if start else 0.0
        tracer.log(
            "http_response",
            {
                "url": str(response.request.url),
                "status": response.status_code,
                "latency_s": round(latency, 4),
                "body": _decode_body(body_bytes),
            },
        )

    return httpx.Client(
        event_hooks={"request": [request_hook], "response": [response_hook]},
        **kwargs,
    )


def make_traced_openai(tracer) -> OpenAI:
    """返回一个 OpenAI client,HTTP 流量全程被 tracer 记录。"""
    if tracer is None:
        return OpenAI()
    timeout = float(os.getenv("OPENAI_TIMEOUT_S", "600"))
    return OpenAI(http_client=make_traced_client(tracer, timeout=timeout))
