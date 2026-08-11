"""
Trace Viewer:浏览器里查看 traces/ 目录下所有 jsonl 文件。

启动:
    python trace_server.py
    # 默认 http://127.0.0.1:8088,可设 TRACE_PORT 改端口

特性:
    - 左侧:trace 文件列表(按修改时间倒序)
    - 右侧:事件时间线 + 顶部统计(总 token、LLM 延迟、HTTP/MCP/Tool 调用次数)
    - 每条事件可点击展开,查看完整 data(包括 HTTP body)
    - "Auto-refresh" 复选框开启后每 3 秒刷新,适合一边跑 agent 一边看
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route


TRACES_DIR = Path(__file__).parent / "traces"


# ---------------------------------------------------------------------------
# Chat:在 server 进程里 spawn agent 跑一轮 prompt
# ---------------------------------------------------------------------------

# Agent 用了模块级 _current_tracer / sys.path,多个并发 run 会互相覆盖,加全局锁
_AGENT_LOCK = threading.Lock()
_AGENT_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def _extract_steps(trace_path: Path) -> tuple[list[dict], int, float]:
    """从 trace jsonl 文件提取 ReAct 步骤(llm_call + tool_call 按 step 配对)。

    返回 (steps, total_tokens, elapsed_s),其中 steps:
        [
          {"step": 1, "thought": "...", "tokens": 123, "llm_latency_s": 0.5,
           "tool": {"name": "...", "arguments": {...}, "result": "...",
                    "latency_s": 0.2, "is_error": False}},
          ...
        ]
    只取 actor=="outer" 或无 actor 的事件,避免嵌套 multi-agent 内部步骤污染主步骤。
    """
    if not trace_path.exists():
        return [], 0, 0.0
    steps: dict[int, dict] = {}
    final: str | None = None
    total_tokens = 0
    elapsed = 0.0
    try:
        text = trace_path.read_text(encoding="utf-8")
    except Exception:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ev = rec.get("event")
        d = rec.get("data") or {}
        # 只关心 outer 主流程的步骤(忽略嵌套 multi-agent 内部)
        actor = d.get("actor")
        if actor and actor != "outer":
            continue
        step_no = d.get("step")
        if ev == "llm_call" and step_no is not None:
            s = steps.setdefault(int(step_no), {"step": int(step_no)})
            s["thought"] = d.get("thought") or ""
            s["tokens"] = d.get("total_tokens", 0)
            s["llm_latency_s"] = d.get("latency_s", 0)
        elif ev == "tool_call" and step_no is not None:
            s = steps.setdefault(int(step_no), {"step": int(step_no)})
            s["tool"] = {
                "name": d.get("name"),
                "arguments": d.get("arguments"),
                "result": d.get("result_preview") or "",
                "latency_s": d.get("latency_s", 0),
                "is_error": bool(d.get("is_error")),
            }
        elif ev == "run_end":
            final = d.get("final_answer")
            total_tokens = d.get("total_tokens", 0)
            elapsed = d.get("elapsed_s", 0)
    ordered = [steps[k] for k in sorted(steps.keys())]
    _ = final  # 已通过 answer 字段返回,这里仅为可读性保留解析
    return ordered, total_tokens, elapsed


def _run_agent_blocking(
    prompt: str,
    session: str,
    use_mcp: bool,
    use_memory: bool,
) -> dict:
    """同步跑一次 agent,返回最终结果 dict。在线程池里调用,持锁。"""
    from dotenv import load_dotenv

    load_dotenv()
    # 延迟 import,避免模块加载时把 agent 整个拉起来
    from agent import Agent, AgentConfig

    cfg = AgentConfig(
        use_trace=True,
        use_mcp=use_mcp,
        use_memory=use_memory,
        session_id=session,
        verbose=False,
    )
    with _AGENT_LOCK:
        agent = Agent(cfg)
        try:
            answer = agent.run(prompt)
        finally:
            agent.close()

    steps, total_tokens, elapsed = _extract_steps(TRACES_DIR / f"{session}.jsonl")
    return {
        "answer": answer,
        "trace_session": session,
        "steps": steps,
        "total_tokens": total_tokens,
        "elapsed_s": elapsed,
    }


async def get_chat_result(request: Request) -> JSONResponse:
    """查 trace_session 对应的 agent 是否已经跑完。
    用于 chat 页在用户跳走再回来时,轮询恢复 pending 请求的结果。
    """
    name = request.path_params.get("trace_session", "")
    if not name or not all(ch.isalnum() or ch in "-_." for ch in name) or ".." in name:
        return JSONResponse({"error": "invalid trace_session"}, status_code=400)
    path = TRACES_DIR / f"{name}.jsonl"
    if not path.exists():
        return JSONResponse({"status": "pending", "reason": "trace not yet started"})
    final_data = None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return JSONResponse({"status": "pending", "reason": f"read error: {e}"})
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("event") == "run_end":
            final_data = rec.get("data") or {}
            break
    if final_data is None:
        return JSONResponse({"status": "pending", "reason": "no run_end yet"})
    steps, total_tokens, elapsed = _extract_steps(path)
    return JSONResponse({
        "status": "done",
        "answer": final_data.get("final_answer", ""),
        "trace_session": name,
        "steps": steps,
        "total_tokens": total_tokens,
        "elapsed_s": elapsed,
    })


async def post_chat(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "empty prompt"}, status_code=400)

    session_base = body.get("session") or ("web-" + uuid.uuid4().hex[:6])
    turn = int(body.get("turn") or 1)
    use_mcp = bool(body.get("use_mcp"))
    use_memory = bool(body.get("use_memory"))

    # 每轮用独立 trace 文件:<session>-001.jsonl
    trace_session = f"{session_base}-{turn:03d}"

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _AGENT_EXECUTOR,
            _run_agent_blocking,
            prompt,
            trace_session,
            use_mcp,
            use_memory,
        )
    except Exception as exc:
        return JSONResponse(
            {"error": f"{type(exc).__name__}: {exc}"}, status_code=500
        )

    return JSONResponse(
        {
            "answer": result["answer"],
            "trace_session": result["trace_session"],
            "session": session_base,
            "turn": turn,
            "steps": result.get("steps", []),
            "total_tokens": result.get("total_tokens", 0),
            "elapsed_s": result.get("elapsed_s", 0),
        }
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


async def list_traces(request: Request) -> JSONResponse:
    if not TRACES_DIR.exists():
        return JSONResponse([])
    files = sorted(
        TRACES_DIR.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    items = []
    for f in files:
        try:
            n = sum(1 for _ in f.open("r", encoding="utf-8"))
        except Exception:
            n = 0
        items.append(
            {
                "name": f.stem,
                "size": f.stat().st_size,
                "mtime": f.stat().st_mtime,
                "events": n,
            }
        )
    return JSONResponse(items)


async def get_trace(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    path = TRACES_DIR / f"{name}.jsonl"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return JSONResponse({"name": name, "events": events})


async def index(request: Request) -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


async def chat_index(request: Request) -> HTMLResponse:
    return HTMLResponse(CHAT_HTML)


# ---------------------------------------------------------------------------
# HTML(内嵌,单文件部署)
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Hello-Agent Trace Viewer</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  :root {
    --bg: #0d1117;
    --bg-elev: #161b22;
    --bg-elev2: #1c2128;
    --border: #30363d;
    --border-strong: #484f58;
    --fg: #c9d1d9;
    --fg-muted: #8b949e;
    --accent: #58a6ff;
    --green: #56d364;
    --orange: #f0883e;
    --purple: #d2a8ff;
    --yellow: #e3b341;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }
  .header {
    padding: 14px 24px;
    background: var(--bg-elev);
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .header h1 { margin: 0; font-size: 17px; font-weight: 600; }
  .header-actions { display: flex; gap: 14px; align-items: center; font-size: 13px; color: var(--fg-muted); }
  .header-actions input[type=checkbox] { vertical-align: middle; }
  .header-actions button {
    background: var(--bg-elev2);
    color: var(--fg);
    border: 1px solid var(--border);
    padding: 5px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
  }
  .header-actions button:hover { background: var(--border); }

  .container { display: flex; height: calc(100vh - 53px); }
  .sidebar {
    width: 260px;
    flex-shrink: 0;
    background: var(--bg-elev);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding: 8px 0;
  }
  .sidebar-item {
    padding: 10px 18px;
    cursor: pointer;
    border-left: 3px solid transparent;
    font-size: 13px;
    word-break: break-all;
  }
  .sidebar-item:hover { background: var(--bg-elev2); }
  .sidebar-item.active {
    background: var(--bg-elev2);
    border-left-color: var(--accent);
  }
  .sidebar-item .meta { color: var(--fg-muted); font-size: 11px; margin-top: 2px; }
  .sidebar-item.dim { opacity: 0.55; }
  .sidebar-item.dim:hover { opacity: 1; }
  .empty {
    text-align: center;
    color: var(--fg-muted);
    padding: 40px 20px;
    font-size: 13px;
  }

  .main { flex: 1; overflow-y: auto; padding: 24px 32px; }
  .trace-title { font-size: 19px; font-weight: 600; margin: 0 0 4px 0; }
  .trace-sub { color: var(--fg-muted); font-size: 13px; margin-bottom: 18px; }

  .stats {
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 18px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 14px;
  }
  .stat .label { color: var(--fg-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
  .stat .value { font-size: 20px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }

  .filter-bar {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }
  .filter-chip {
    padding: 4px 10px;
    border-radius: 12px;
    background: var(--bg-elev);
    border: 1px solid var(--border);
    color: var(--fg-muted);
    font-size: 11px;
    cursor: pointer;
    user-select: none;
  }
  .filter-chip.on { background: var(--bg-elev2); color: var(--fg); border-color: var(--border-strong); }

  .timeline { display: flex; flex-direction: column; gap: 6px; }
  .event {
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    cursor: pointer;
    transition: border-color 0.12s;
  }
  .event:hover { border-color: var(--border-strong); }
  .event-time {
    font-family: ui-monospace, 'SF Mono', Monaco, 'Cascadia Code', monospace;
    color: var(--fg-muted);
    font-size: 12px;
    min-width: 60px;
    padding-top: 1px;
  }
  .event-tag {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    min-width: 116px;
    text-align: center;
    flex-shrink: 0;
    font-family: ui-monospace, 'SF Mono', monospace;
  }
  .tag-mcp { background: rgba(189, 147, 249, 0.15); color: var(--purple); }
  .tag-http { background: rgba(88, 166, 255, 0.15); color: var(--accent); }
  .tag-llm { background: rgba(63, 185, 80, 0.15); color: var(--green); }
  .tag-tool { background: rgba(247, 147, 30, 0.15); color: var(--orange); }
  .tag-run { background: rgba(139, 148, 158, 0.15); color: var(--fg-muted); }

  .event-body { flex: 1; min-width: 0; }
  .event-summary {
    font-size: 13px;
    word-break: break-all;
  }
  .event-detail {
    margin-top: 10px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 12px;
    font-family: ui-monospace, 'SF Mono', monospace;
    font-size: 11.5px;
    line-height: 1.55;
    white-space: pre-wrap;
    overflow-x: auto;
    display: none;
    color: #e6edf3;
  }
  .event.expanded .event-detail { display: block; }

  .event-detail .k { color: #ff7b72; }
  .event-detail .s { color: #a5d6ff; }
  .event-detail .n { color: #79c0ff; }
  .event-detail .b { color: #ffa657; }

  .flow-section {
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 18px;
    overflow: hidden;
  }
  .flow-header {
    padding: 10px 16px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    user-select: none;
    border-bottom: 1px solid var(--border);
  }
  .flow-header:hover { background: var(--bg-elev2); }
  .flow-header .title { font-size: 14px; font-weight: 600; }
  .flow-header .caret { color: var(--fg-muted); font-size: 12px; transition: transform 0.15s; }
  .flow-section.collapsed .flow-header { border-bottom: none; }
  .flow-section.collapsed .caret { transform: rotate(-90deg); }
  .flow-body {
    padding: 16px;
    overflow-x: auto;
    background: var(--bg);
    text-align: center;
  }
  .flow-section.collapsed .flow-body { display: none; }
  .flow-body svg { max-width: 100%; height: auto; }
  .flow-body .err {
    color: #ff7b72;
    font-family: ui-monospace, monospace;
    font-size: 12px;
    text-align: left;
    white-space: pre-wrap;
  }
</style>
</head>
<body>

<div class="header">
  <h1>🔍 Hello-Agent Trace Viewer</h1>
  <div class="header-actions">
    <span id="sessionTag" style="display:none;font-family:ui-monospace,monospace;font-size:12px;background:var(--bg-elev2);padding:4px 10px;border-radius:6px;border:1px solid var(--border);">session: <span id="sessionTagName" style="color:var(--accent);"></span></span>
    <a id="chatLink" href="/chat" style="color:var(--fg);text-decoration:none;padding:5px 12px;background:var(--bg-elev2);border:1px solid var(--border);border-radius:6px;font-size:13px;">💬 Chat</a>
    <button onclick="newChatSession()" title="开始一个新的 chat session">🆕 新会话</button>
    <label><input type="checkbox" id="autoRefresh"> 自动刷新 (3s)</label>
    <button onclick="refresh()">刷新</button>
  </div>
</div>

<div class="container">
  <div class="sidebar-wrap" style="display:flex;flex-direction:column;width:260px;flex-shrink:0;background:var(--bg-elev);border-right:1px solid var(--border);">
    <div style="padding:8px 12px;border-bottom:1px solid var(--border);">
      <label style="display:block;font-size:11px;color:var(--fg-muted);margin-bottom:4px;">Filter by session</label>
      <div style="display:flex;gap:4px;">
        <input id="sessionFilter" type="text" placeholder="(all)" style="flex:1;background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:3px 8px;font-size:12px;font-family:ui-monospace,monospace;min-width:0;">
        <button id="sessionFilterClear" title="清除过滤" style="background:var(--bg-elev2);color:var(--fg-muted);border:1px solid var(--border);border-radius:4px;padding:3px 8px;font-size:12px;cursor:pointer;">✕</button>
      </div>
    </div>
    <div class="sidebar" id="sidebar" style="flex:1;overflow-y:auto;padding:8px 0;">Loading…</div>
  </div>
  <div class="main" id="main">
    <div class="empty">从左侧选一个 trace 查看。<br><br>没有文件?跑一下:<br><code>$env:AGENT_USE_TRACE="1"; python main.py "..."</code><br>或者打开 <a href="/chat" style="color:var(--accent);">💬 Chat</a></div>
  </div>
</div>

<script>
let activeName = null;
let activeFilters = new Set(['all']);
let flowCollapsed = false;
let mermaidRenderSeq = 0;

if (window.mermaid) {
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    securityLevel: 'loose',
    sequence: { mirrorActors: false, showSequenceNumbers: true, actorMargin: 80 },
  });
}

function escMermaid(s) {
  // mermaid sequence message:换行/分号会断句;反斜杠会被当转义;# 是注释起始
  // 保留 ":" 因为时间串 / args 里很常见
  return String(s)
    .replace(/[\n\r]+/g, ' ')
    .replace(/\\/g, '/')
    .replace(/[<>#;"]/g, '')
    .trim() || ' ';
}

// actor → lifeline 简称
function actorLifeline(actor) {
  if (!actor || actor === 'outer') return 'A';
  if (actor === 'supervisor') return 'S';
  if (actor === 'synthesizer') return 'Y';
  if (typeof actor === 'string' && actor.startsWith('worker-')) return 'W';
  return 'A';
}

function actorLabel(actor, agentName) {
  const fallback = agentName || 'Hello-Agent';
  if (!actor || actor === 'outer') return fallback;
  if (actor === 'supervisor') return 'Supervisor';
  if (actor === 'synthesizer') return 'Synthesizer';
  if (typeof actor === 'string' && actor.startsWith('worker-')) {
    return 'Worker (' + actor.slice('worker-'.length) + ')';
  }
  return fallback;
}

// 扫 events 提取主 LLM 模型名集合(从 outer 的 llm_call.data.model)
function detectModels(events) {
  const models = [];
  const seen = new Set();
  for (const e of events) {
    if (e.event === 'llm_call' && e.data && e.data.model) {
      const m = String(e.data.model);
      if (!seen.has(m)) { seen.add(m); models.push(m); }
    }
  }
  return models;
}

// 从 URL 提取 host(包括端口)
function extractHost(url) {
  if (typeof url !== 'string') return null;
  const m = url.match(/^https?:\/\/([^\/?#]+)/i);
  return m ? m[1] : null;
}

// 截掉 host,只保留 path?query
function urlPath(url) {
  if (typeof url !== 'string') return '/';
  return url.replace(/^https?:\/\/[^\/?#]+/i, '') || '/';
}

function buildMermaidFlow(events) {
  // 收集 outer llm_call 的时间戳,用于 http_request/response 去重
  // (outer agent.py 在 http_response 之后立即 log llm_call,所以两者时间很接近)
  const outerLLMCallTs = events
    .filter(e => e.event === 'llm_call')
    .map(e => e.ts);
  const isCoveredByOuterLLM = (ts) =>
    outerLLMCallTs.some(t => Math.abs(t - ts) < 0.5);

  const isLLMUrl = (u) =>
    typeof u === 'string' && (u.includes('/chat/completions') || /\/completions(\?|$)/.test(u));
  const isEmbedUrl = (u) =>
    typeof u === 'string' && u.includes('/embeddings');

  // 提取主 LLM 模型名(用于动态 lifeline 标签)
  const models = detectModels(events);
  const llmLabel = models.length === 0
    ? 'LLM'
    : models.length === 1
    ? models[0]
    : `${models[0]} / ${models[1]}${models.length > 2 ? ' …' : ''}`;
  const agentLabel = models.length
    ? `Hello-Agent · ${models[0]}`
    : 'Hello-Agent';

  // 扫一遍,确定要展示哪些 lifeline + 收集外部 host
  const usedLanes = new Set(['U', 'A']);
  let hasLLM = false, hasTool = false;
  let workerNames = new Set();
  // 外部 host(tool 访问的远端服务器):host -> lifeline ID (H1/H2/...)
  const externalHosts = new Map();
  let hostIdx = 1;
  for (const e of events) {
    const d = e.data || {};
    const lane = actorLifeline(d.actor);
    usedLanes.add(lane);
    if (typeof d.actor === 'string' && d.actor.startsWith('worker-')) {
      workerNames.add(d.actor.slice('worker-'.length));
    }
    if (e.event === 'llm_call') hasLLM = true;
    if (e.event === 'tool_call') hasTool = true;
    if (e.event === 'http_request' || e.event === 'http_response') {
      const url = d.url || '';
      if (isLLMUrl(url) || isEmbedUrl(url)) {
        hasLLM = true;
      } else if (url) {
        hasTool = true;
        const host = extractHost(url);
        if (host && !externalHosts.has(host)) {
          externalHosts.set(host, 'H' + (hostIdx++));
        }
      }
    }
  }

  // 是否有 MCP 事件 → 决定 MCP lifeline 是否展示
  const hasMCP = events.some(e =>
    e.event === 'mcp_initialize' || e.event === 'mcp_request' || e.event === 'mcp_response'
  );

  // 把每个 (外部 http) 和 (mcp_request/response) 都关联到对应 tool_call(基于时间戳)
  // 让 sequence 图按 "A→T → T→host/M → host/M→T → T→A" 的逻辑顺序展示
  const absorbedHttp = new Set();   // 索引集合
  const absorbedMcp = new Set();
  const toolHttpMap = new Map();    // tool_call idx -> [http idx]
  const toolMcpMap = new Map();     // tool_call idx -> [mcp idx]
  let lastBoundary = events[0]?.ts || 0;
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (e.event === 'tool_call') {
      const httpIdx = [];
      const mcpIdx = [];
      for (let j = 0; j < i; j++) {
        const k = events[j];
        if (k.ts < lastBoundary || k.ts > e.ts) continue;
        if (!absorbedHttp.has(j) && (k.event === 'http_request' || k.event === 'http_response')) {
          const url = k.data?.url || '';
          if (url && !isLLMUrl(url) && !isEmbedUrl(url)) {
            httpIdx.push(j);
            absorbedHttp.add(j);
          }
        }
        if (!absorbedMcp.has(j) && (k.event === 'mcp_request' || k.event === 'mcp_response')) {
          mcpIdx.push(j);
          absorbedMcp.add(j);
        }
      }
      toolHttpMap.set(i, httpIdx);
      toolMcpMap.set(i, mcpIdx);
      lastBoundary = e.ts;
    } else if (e.event === 'llm_call' || e.event === 'run_start') {
      lastBoundary = Math.max(lastBoundary, e.ts);
    }
  }

  // participant alias 用双引号包裹,避免 model 名里的 ':' 之类字符
  // 与 Mermaid 的 message 分隔符冲突
  const pq = (label) => `"${escMermaid(label)}"`;

  const lines = ['sequenceDiagram'];
  lines.push('  participant U as User');
  lines.push(`  participant A as ${pq(agentLabel)}`);
  if (usedLanes.has('S')) lines.push('  participant S as Supervisor');
  if (usedLanes.has('W')) {
    const wlabel = workerNames.size === 1
      ? `Worker- ${[...workerNames][0]}`
      : `Worker [${[...workerNames].slice(0, 3).join('/')}${workerNames.size > 3 ? ' ...' : ''}]`;
    lines.push(`  participant W as ${pq(wlabel)}`);
  }
  if (usedLanes.has('Y')) lines.push('  participant Y as Synthesizer');
  if (hasLLM) lines.push(`  participant L as ${pq(llmLabel)}`);
  if (hasTool) lines.push('  participant T as Tool');
  if (hasMCP) lines.push(`  participant M as ${pq('MCP Server')}`);
  // 每个外部 host 一条 lifeline(放在 Tool/MCP 右侧)
  for (const [host, hid] of externalHosts) {
    lines.push(`  participant ${hid} as ${pq(host)}`);
  }

  // 第一次出现 supervisor / worker / synthesizer 时,从 A 画一根"委派"箭头
  const delegated = new Set();
  function delegateOnce(targetLane, label) {
    if (!targetLane || targetLane === 'A' || delegated.has(targetLane)) return;
    delegated.add(targetLane);
    lines.push(`  A->>${targetLane}: ${escMermaid(label)}`);
  }

  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    const d = e.data || {};
    const lane = actorLifeline(d.actor);

    // 该 http / mcp 事件已被对应的 tool_call 吸收 → 跳过(由 tool_call 统一渲染)
    if ((e.event === 'http_request' || e.event === 'http_response') && absorbedHttp.has(i)) {
      continue;
    }
    if ((e.event === 'mcp_request' || e.event === 'mcp_response') && absorbedMcp.has(i)) {
      continue;
    }

    switch (e.event) {
      case 'mcp_initialize': {
        const tools = (d.tools || []).slice(0, 4).join(', ');
        const more = (d.tools || []).length > 4 ? ` +${d.tools.length - 4} more` : '';
        lines.push(`  Note over A: MCP init- ${escMermaid(tools)}${more}`);
        break;
      }
      case 'run_start':
        lines.push(`  U->>A: ${escMermaid((d.user_input || '').slice(0, 70))}`);
        break;
      case 'llm_call': {
        const tokens = `${d.prompt_tokens || 0}→${d.completion_tokens || 0} tok · ${d.latency_s}s`;
        lines.push(`  ${lane}->>L: chat completions [step ${d.step}]`);
        lines.push(`  Note right of L: ${escMermaid(tokens)}`);
        const reply = (d.thought || '').trim();
        if (reply) {
          lines.push(`  L-->>${lane}: ${escMermaid(reply.slice(0, 60))}`);
        } else {
          lines.push(`  L-->>${lane}: (tool_calls)`);
        }
        break;
      }
      case 'tool_call': {
        const argsStr = typeof d.arguments === 'string'
          ? d.arguments
          : JSON.stringify(d.arguments || {});
        const errTag = d.is_error ? ' [ERROR]' : '';
        // 如果 tool_call 来自 outer 且工具是 research_topic(或同类 meta-tool),
        // 在画 outer→Tool 之前先画一条"委派"箭头到 Supervisor / Worker
        if (lane === 'A' && d.name === 'research_topic') {
          delegateOnce('S', 'spawn multi-agent');
        }
        lines.push(`  ${lane}->>T: ${escMermaid(d.name)}(${escMermaid(argsStr.slice(0, 36))})${errTag}`);

        // 如果该 tool 内部调用了 MCP server,把 mcp_request/response 画进来
        const innerMcp = toolMcpMap.get(i) || [];
        for (const j of innerMcp) {
          const m = events[j];
          const md = m.data || {};
          if (m.event === 'mcp_request') {
            const aStr = typeof md.arguments === 'string'
              ? md.arguments
              : JSON.stringify(md.arguments || {});
            const head = (md.method || 'tools/call') + ' ' + (md.name || '');
            lines.push(`  T->>M: ${escMermaid(head + '(' + aStr.slice(0, 30) + ')')}`);
          } else if (m.event === 'mcp_response') {
            const lat = md.latency_s !== undefined ? ` ${md.latency_s}s` : '';
            const preview = (md.result_preview || '').replace(/\s+/g, ' ').slice(0, 40);
            lines.push(`  M-->>T: ${escMermaid(preview)}${lat}`);
          }
        }

        // 如果该 tool 内部调用了外部 HTTP,把那些"远端服务器"的请求/响应画进来
        const innerHttp = toolHttpMap.get(i) || [];
        for (const j of innerHttp) {
          const h = events[j];
          const hd = h.data || {};
          const url = hd.url || '';
          const host = extractHost(url);
          if (!host || !externalHosts.has(host)) continue;
          const hid = externalHosts.get(host);
          if (h.event === 'http_request') {
            const path = urlPath(url);
            const method = hd.method || 'GET';
            lines.push(`  T->>${hid}: ${escMermaid(method + ' ' + path.slice(0, 50))}`);
          } else if (h.event === 'http_response') {
            const lat = hd.latency_s !== undefined ? ` ${hd.latency_s}s` : '';
            const sz = hd.bytes !== undefined ? ` ${hd.bytes}B` : '';
            lines.push(`  ${hid}-->>T: ${hd.status || ''}${sz}${lat}`);
          }
        }

        const result = (d.result_preview || '').replace(/\s+/g, ' ');
        lines.push(`  T-->>${lane}: ${escMermaid(result.slice(0, 50))}`);
        break;
      }
      case 'http_request': {
        if (isCoveredByOuterLLM(e.ts)) break;
        const url = d.url || '';
        // 到达新 actor lifeline 时画一根委派箭头
        if (lane === 'S') delegateOnce('S', 'route subtask');
        else if (lane === 'W') delegateOnce('W', 'subtask');
        else if (lane === 'Y') delegateOnce('Y', 'synthesize');

        if (isLLMUrl(url)) {
          lines.push(`  ${lane}->>L: chat completions`);
        } else if (isEmbedUrl(url)) {
          lines.push(`  ${lane}->>L: embeddings`);
        } else {
          // 没被 tool_call 吸收的外部 http(比如 multi-agent 内部 worker 直接调外部 API)
          // → 画成 lane→host 直连
          const host = extractHost(url);
          const hid = host && externalHosts.get(host);
          if (hid) {
            lines.push(`  ${lane}->>${hid}: ${escMermaid((d.method || 'GET') + ' ' + urlPath(url).slice(0, 50))}`);
          } else {
            lines.push(`  ${lane}->>T: ${escMermaid(d.method || 'GET')} ${escMermaid(url.slice(0, 50))}`);
          }
        }
        break;
      }
      case 'http_response': {
        const reqTs = e.ts - (d.latency_s || 0);
        if (isCoveredByOuterLLM(reqTs)) break;
        const url = d.url || '';
        const lat = d.latency_s !== undefined ? `${d.latency_s}s` : '';
        if (isLLMUrl(url)) {
          lines.push(`  L-->>${lane}: HTTP ${d.status} ${lat}`);
        } else if (isEmbedUrl(url)) {
          lines.push(`  L-->>${lane}: vector ${lat}`);
        } else {
          const host = extractHost(url);
          const hid = host && externalHosts.get(host);
          if (hid) {
            lines.push(`  ${hid}-->>${lane}: HTTP ${d.status || ''} ${lat}`);
          } else {
            lines.push(`  T-->>${lane}: HTTP ${d.status} ${lat}`);
          }
        }
        break;
      }
      case 'mcp_request': {
        // 没被 tool_call 吸收时(极端情况)直接 lane→M
        const aStr = typeof d.arguments === 'string'
          ? d.arguments
          : JSON.stringify(d.arguments || {});
        const head = (d.method || 'tools/call') + ' ' + (d.name || '');
        lines.push(`  ${lane}->>M: ${escMermaid(head + '(' + aStr.slice(0, 30) + ')')}`);
        break;
      }
      case 'mcp_response': {
        const lat = d.latency_s !== undefined ? ` ${d.latency_s}s` : '';
        const preview = (d.result_preview || '').replace(/\s+/g, ' ').slice(0, 40);
        lines.push(`  M-->>${lane}: ${escMermaid(preview)}${lat}`);
        break;
      }
      case 'run_end':
        lines.push(`  A-->>U: ${escMermaid((d.final_answer || '').slice(0, 70))}`);
        break;
    }
  }

  // 没有任何可呈现的高层事件 → 给个占位
  const headerLines = 1 + usedLanes.size
                    + (hasLLM ? 1 : 0)
                    + (hasTool ? 1 : 0)
                    + (hasMCP ? 1 : 0)
                    + externalHosts.size;
  if (lines.length <= headerLines) {
    lines.push('  Note over U,A: (no high-level run events; check timeline)');
  }
  return lines.join('\n');
}

async function renderFlow(containerId, events) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!window.mermaid) {
    container.innerHTML = '<div class="err">mermaid 未加载(检查网络/CDN)</div>';
    return;
  }
  const text = buildMermaidFlow(events);
  const renderId = 'mermaid-svg-' + (++mermaidRenderSeq);
  try {
    const { svg } = await mermaid.render(renderId, text);
    container.innerHTML = svg;
  } catch (err) {
    container.innerHTML =
      '<div class="err">flow 渲染失败:\n' +
      escapeHtml(String(err && err.message ? err.message : err)) +
      '\n\n--- mermaid source ---\n' +
      escapeHtml(text) +
      '</div>';
  }
}

async function fetchTraces() {
  const r = await fetch('/api/traces');
  return r.json();
}
async function fetchTrace(name) {
  const r = await fetch('/api/traces/' + encodeURIComponent(name));
  return r.json();
}

function tagClass(event) {
  if (event.startsWith('mcp_')) return 'tag-mcp';
  if (event.startsWith('http_')) return 'tag-http';
  if (event === 'llm_call') return 'tag-llm';
  if (event === 'tool_call') return 'tag-tool';
  return 'tag-run';
}

function eventCategory(event) {
  if (event.startsWith('mcp_')) return 'mcp';
  if (event.startsWith('http_')) return 'http';
  if (event === 'llm_call') return 'llm';
  if (event === 'tool_call') return 'tool';
  return 'run';
}

function summarizeEvent(e) {
  const d = e.data || {};
  switch (e.event) {
    case 'run_start': return 'task: ' + (d.user_input || '').slice(0, 200);
    case 'run_end':
      return `final: ${(d.final_answer || '').slice(0, 100)} · tokens=${d.total_tokens} · ${d.elapsed_s}s`;
    case 'llm_call':
      return `step ${d.step} · ${d.model} · prompt=${d.prompt_tokens} completion=${d.completion_tokens} total=${d.total_tokens} · ${d.latency_s}s` +
        (d.thought ? ` · "${(d.thought || '').replace(/\s+/g, ' ').slice(0, 80)}"` : '');
    case 'tool_call':
      return `step ${d.step} · ${d.name}(${typeof d.arguments === 'string' ? d.arguments.slice(0, 80) : JSON.stringify(d.arguments).slice(0, 80)}) · ${d.latency_s}s` +
        (d.is_error ? ' · ERROR' : '');
    case 'http_request':
      return `${d.method} ${d.url}`;
    case 'http_response':
      return `← ${d.status} ${d.url} · ${d.latency_s}s`;
    case 'mcp_initialize':
      return `tools: ${(d.tools || []).join(', ')}`;
    case 'mcp_request':
      return `${d.method} ${d.name || ''}`;
    case 'mcp_response':
      return `${d.method} ${d.name || ''} · ${d.latency_s}s`;
    default:
      return JSON.stringify(d).slice(0, 200);
  }
}

function buildStats(events) {
  let totalTokens = 0, llmLatency = 0, httpReq = 0, mcpCalls = 0, toolCalls = 0, elapsed = 0, llmCalls = 0;
  for (const e of events) {
    if (e.event === 'llm_call') {
      totalTokens += e.data.total_tokens || 0;
      llmLatency += e.data.latency_s || 0;
      llmCalls++;
    }
    if (e.event === 'http_request') httpReq++;
    if (e.event === 'mcp_request') mcpCalls++;
    if (e.event === 'tool_call') toolCalls++;
    if (e.event === 'run_end') elapsed = e.data.elapsed_s || 0;
  }
  const stats = [
    ['Events', events.length],
    ['LLM Calls', llmCalls],
    ['Tokens', totalTokens],
    ['LLM Latency', llmLatency.toFixed(2) + 's'],
    ['HTTP', httpReq],
    ['MCP', mcpCalls],
    ['Tools', toolCalls],
    ['Elapsed', elapsed.toFixed(2) + 's'],
  ];
  return stats.map(([l, v]) =>
    `<div class="stat"><div class="label">${l}</div><div class="value">${v}</div></div>`
  ).join('');
}

function escapeHtml(text) {
  // 1) 剥离 ANSI 转义序列(终端着色,如 wttr.in 返回的 \x1b[38;5;226m...)
  // 2) 剥离不可打印的 C0 控制字符(保留 \t \n \r)
  // 3) HTML 转义
  let s = String(text == null ? '' : text)
    .replace(/\x1b\[[\d;]*[A-Za-z]/g, '')
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function highlightJson(jsonStr) {
  // 简单的 JSON 高亮(key/string/number/bool)
  return jsonStr
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*")\s*:/g, '<span class="k">$1</span>:')
    .replace(/:\s*("(?:\\.|[^"\\])*")/g, ': <span class="s">$1</span>')
    .replace(/:\s*(true|false|null)/g, ': <span class="b">$1</span>')
    .replace(/:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, ': <span class="n">$1</span>');
}

function renderTrace(data) {
  const main = document.getElementById('main');
  const events = data.events || [];
  if (!events.length) {
    main.innerHTML = '<div class="empty">empty trace</div>';
    return;
  }
  const t0 = events[0].ts;
  const cats = ['all', 'run', 'llm', 'http', 'tool', 'mcp'];
  const filterHtml = cats.map(c =>
    `<div class="filter-chip ${activeFilters.has(c) ? 'on' : ''}" data-cat="${c}">${c}</div>`
  ).join('');

  const eventsHtml = events.map((e, i) => {
    const cat = eventCategory(e.event);
    const visible = activeFilters.has('all') || activeFilters.has(cat);
    const detail = highlightJson(JSON.stringify(e.data, null, 2));
    return `
      <div class="event" data-idx="${i}" data-cat="${cat}" style="${visible ? '' : 'display:none'}">
        <div class="event-time">+${(e.ts - t0).toFixed(2)}s</div>
        <div class="event-tag ${tagClass(e.event)}">${e.event}</div>
        <div class="event-body">
          <div class="event-summary">${escapeHtml(summarizeEvent(e))}</div>
          <div class="event-detail">${detail}</div>
        </div>
      </div>
    `;
  }).join('');

  const flowContainerId = 'flow-svg-' + (mermaidRenderSeq + 1);

  main.innerHTML = `
    <div class="trace-title">${escapeHtml(data.name)}</div>
    <div class="trace-sub">${events.length} events</div>
    <div class="stats">${buildStats(events)}</div>
    <div class="flow-section ${flowCollapsed ? 'collapsed' : ''}" id="flowSection">
      <div class="flow-header" id="flowHeader">
        <span class="title">Call Flow (sequence diagram)</span>
        <span class="caret">▼</span>
      </div>
      <div class="flow-body" id="${flowContainerId}">rendering…</div>
    </div>
    <div class="filter-bar">${filterHtml}</div>
    <div class="timeline">${eventsHtml}</div>
  `;

  main.querySelectorAll('.event').forEach(el => {
    el.onclick = () => el.classList.toggle('expanded');
  });
  main.querySelectorAll('.filter-chip').forEach(el => {
    el.onclick = () => {
      const cat = el.dataset.cat;
      if (cat === 'all') {
        activeFilters = new Set(['all']);
      } else {
        activeFilters.delete('all');
        if (activeFilters.has(cat)) activeFilters.delete(cat);
        else activeFilters.add(cat);
        if (activeFilters.size === 0) activeFilters = new Set(['all']);
      }
      renderTrace(data);
    };
  });

  document.getElementById('flowHeader').onclick = () => {
    flowCollapsed = !flowCollapsed;
    document.getElementById('flowSection').classList.toggle('collapsed', flowCollapsed);
  };

  // 异步渲染 mermaid(不阻塞主体)
  renderFlow(flowContainerId, events);
}

function getActiveSessionFilter() {
  const v = (document.getElementById('sessionFilter')?.value || '').trim();
  return v;
}

async function loadSidebar() {
  const traces = await fetchTraces();
  if (!traces.length) {
    document.getElementById('sidebar').innerHTML =
      '<div class="empty">没有 trace 文件。<br>跑 agent 时加上<br><code>AGENT_USE_TRACE=1</code><br>或打开 <a href="/chat" style="color:var(--accent);">💬 Chat</a></div>';
    return;
  }
  const filter = getActiveSessionFilter();
  // 匹配规则:trace 名以 "<filter>" 或 "<filter>-" 开头
  const matches = (name) => {
    if (!filter) return true;
    return name === filter || name.startsWith(filter + '-');
  };
  const matched = traces.filter(t => matches(t.name));
  const others = traces.filter(t => !matches(t.name));

  const renderItem = (t, dim) => `
    <div class="sidebar-item ${t.name === activeName ? 'active' : ''}${dim ? ' dim' : ''}" data-name="${escapeHtml(t.name)}">
      <div>${escapeHtml(t.name)}</div>
      <div class="meta">${t.events} events · ${(t.size / 1024).toFixed(1)}KB</div>
    </div>
  `;
  let html = '';
  if (filter) {
    html += `<div style="padding:6px 18px;font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.05em;">本会话 (${matched.length})</div>`;
    html += matched.map(t => renderItem(t, false)).join('') ||
            '<div style="padding:8px 18px;font-size:12px;color:var(--fg-muted);">本会话暂无 trace</div>';
    if (others.length) {
      html += `<div style="padding:10px 18px 6px;font-size:11px;color:var(--fg-muted);text-transform:uppercase;letter-spacing:0.05em;border-top:1px solid var(--border);margin-top:6px;">其它 (${others.length})</div>`;
      html += others.map(t => renderItem(t, true)).join('');
    }
  } else {
    html = traces.map(t => renderItem(t, false)).join('');
  }
  document.getElementById('sidebar').innerHTML = html;
  document.getElementById('sidebar').querySelectorAll('.sidebar-item').forEach(el => {
    el.onclick = () => selectTrace(el.dataset.name);
  });
}

function syncChatLinkAndTag() {
  const session = localStorage.getItem('chatSession') || '';
  const link = document.getElementById('chatLink');
  link.href = session ? '/chat?session=' + encodeURIComponent(session) : '/chat';
  const tag = document.getElementById('sessionTag');
  if (session) {
    tag.style.display = '';
    document.getElementById('sessionTagName').textContent = session;
  } else {
    tag.style.display = 'none';
  }
}

function newChatSession() {
  if (!confirm('开始一个新的 chat session?')) return;
  // 跳到 chat 页强制新会话(/chat?new=1 会生成 random session 并写入 localStorage)
  location.href = '/chat?new=1';
}

async function selectTrace(name) {
  activeName = name;
  document.querySelectorAll('.sidebar-item').forEach(el => {
    el.classList.toggle('active', el.dataset.name === name);
  });
  const data = await fetchTrace(name);
  renderTrace(data);
}

async function refresh() {
  await loadSidebar();
  if (activeName) {
    const data = await fetchTrace(activeName);
    renderTrace(data);
  } else {
    // 还没选过 trace 时,自动选 sidebar 第一条(最新)
    const first = document.querySelector('#sidebar .sidebar-item');
    if (first && first.dataset.name) {
      selectTrace(first.dataset.name);
    }
  }
}

document.getElementById('autoRefresh').onchange = (e) => {
  if (e.target.checked) {
    window._refreshTimer = setInterval(refresh, 3000);
  } else {
    clearInterval(window._refreshTimer);
  }
};

// 启动时:同步 URL ?session= 到 localStorage,初始化 filter / chat link,加载 sidebar,如有 ?trace= 自动选中
(async () => {
  const params = new URLSearchParams(location.search);
  const wantSession = params.get('session');
  const wantTrace = params.get('trace');

  if (wantSession) {
    localStorage.setItem('chatSession', wantSession);
  }
  const currentSession = localStorage.getItem('chatSession') || '';
  document.getElementById('sessionFilter').value = currentSession;
  syncChatLinkAndTag();

  // filter 输入框事件
  document.getElementById('sessionFilter').addEventListener('input', () => {
    const v = getActiveSessionFilter();
    if (v) {
      localStorage.setItem('chatSession', v);
    }
    syncChatLinkAndTag();
    loadSidebar();
  });
  document.getElementById('sessionFilterClear').addEventListener('click', () => {
    document.getElementById('sessionFilter').value = '';
    loadSidebar();
  });

  await loadSidebar();
  if (wantTrace) {
    selectTrace(wantTrace);
  } else {
    // 没指定具体 trace 时,自动选 sidebar 第一条
    // sidebar 已经按 mtime 倒序,且当前 session 的 traces 置顶,
    // 所以第一条 = "本会话最新" 或 (无 filter 时) "全局最新"
    const first = document.querySelector('#sidebar .sidebar-item');
    if (first && first.dataset.name) {
      selectTrace(first.dataset.name);
    }
  }
})();

</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Chat HTML
# ---------------------------------------------------------------------------

CHAT_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Hello-Agent Chat</title>
<style>
  :root {
    --bg: #0d1117; --bg-elev: #161b22; --bg-elev2: #1c2128;
    --border: #30363d; --border-strong: #484f58;
    --fg: #c9d1d9; --fg-muted: #8b949e;
    --accent: #58a6ff; --green: #56d364; --orange: #f0883e;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Helvetica, Arial, sans-serif;
    font-size: 14px; height: 100vh; display: flex; flex-direction: column;
  }
  .header {
    padding: 12px 24px; background: var(--bg-elev); border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }
  .header h1 { margin: 0; font-size: 17px; font-weight: 600; }
  .header-actions { display: flex; gap: 12px; align-items: center; font-size: 13px; }
  .header-actions a {
    color: var(--fg); text-decoration: none; padding: 5px 12px;
    background: var(--bg-elev2); border: 1px solid var(--border); border-radius: 6px;
  }
  .header-actions a:hover { background: var(--border); }

  .settings {
    padding: 10px 24px; background: var(--bg-elev); border-bottom: 1px solid var(--border);
    display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--fg-muted);
  }
  .settings label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  .settings input[type=text] {
    background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 4px;
    padding: 3px 8px; font-size: 12px; font-family: ui-monospace, monospace; width: 200px;
  }
  .settings button {
    background: var(--bg-elev2); color: var(--fg); border: 1px solid var(--border); border-radius: 4px;
    padding: 3px 10px; font-size: 12px; cursor: pointer;
  }
  .settings button:hover { background: var(--border); }

  .messages { flex: 1; overflow-y: auto; padding: 24px 32px; max-width: 1100px; width: 100%; margin: 0 auto; }
  .msg { margin-bottom: 16px; display: flex; gap: 12px; }
  .msg-avatar {
    width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-weight: 600; font-size: 14px;
  }
  .msg.user .msg-avatar { background: rgba(88, 166, 255, 0.2); color: var(--accent); }
  .msg.agent .msg-avatar { background: rgba(63, 185, 80, 0.2); color: var(--green); }
  .msg-body { flex: 1; min-width: 0; }
  .msg-role { font-size: 12px; color: var(--fg-muted); margin-bottom: 4px; }
  .msg-content {
    background: var(--bg-elev); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 16px; line-height: 1.6; word-break: break-word; white-space: pre-wrap;
  }
  .msg.agent .msg-content { background: var(--bg-elev2); }
  .msg-content code {
    font-family: ui-monospace, 'SF Mono', monospace; font-size: 90%;
    background: var(--bg); padding: 1px 5px; border-radius: 3px;
  }
  .msg-content pre {
    background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
    padding: 10px; overflow-x: auto; margin: 8px 0;
  }
  .msg-meta { margin-top: 6px; font-size: 11px; color: var(--fg-muted); }
  .msg-meta a {
    color: var(--accent); text-decoration: none;
    background: rgba(88, 166, 255, 0.1); padding: 2px 8px; border-radius: 3px;
    border: 1px solid rgba(88, 166, 255, 0.3);
  }
  .msg-meta a:hover { background: rgba(88, 166, 255, 0.2); }
  .msg-error .msg-content { color: #ff7b72; border-color: rgba(255, 123, 114, 0.4); }
  .typing { color: var(--fg-muted); font-style: italic; animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity: 0.5; } 50% { opacity: 1; } }
  .msg.pending { opacity: 0.85; }

  /* 思考过程折叠区 */
  .thinking {
    margin-bottom: 8px; background: var(--bg);
    border: 1px solid var(--border); border-radius: 6px;
    font-size: 13px; overflow: hidden;
  }
  .thinking > summary {
    cursor: pointer; padding: 8px 12px; user-select: none;
    color: var(--fg-muted); list-style: none;
    display: flex; align-items: center; gap: 8px;
  }
  .thinking > summary::-webkit-details-marker { display: none; }
  .thinking > summary::before {
    content: '▶'; font-size: 9px; transition: transform 0.15s;
    color: var(--fg-muted);
  }
  .thinking[open] > summary::before { transform: rotate(90deg); }
  .thinking > summary:hover { background: var(--bg-elev2); color: var(--fg); }
  .thinking-body { padding: 4px 12px 10px; border-top: 1px solid var(--border); }
  .think-step {
    margin-top: 10px; padding-top: 10px;
    border-top: 1px dashed var(--border);
  }
  .think-step:first-child { margin-top: 4px; padding-top: 4px; border-top: none; }
  .think-step-head {
    font-size: 11px; color: var(--fg-muted); margin-bottom: 4px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }
  .think-step-head .badge {
    display: inline-block; padding: 1px 7px; border-radius: 3px;
    background: rgba(88, 166, 255, 0.15); color: var(--accent);
    margin-right: 6px; font-weight: 600;
  }
  .think-thought {
    color: var(--fg); white-space: pre-wrap;
    line-height: 1.55; margin-bottom: 4px;
  }
  .think-tool {
    margin-top: 6px; padding: 8px 10px;
    background: var(--bg-elev2); border-radius: 4px;
    border-left: 3px solid var(--green);
    font-family: ui-monospace, 'SF Mono', monospace; font-size: 12px;
  }
  .think-tool.is-error { border-left-color: #ff7b72; }
  .think-tool .tool-name { color: var(--green); font-weight: 600; }
  .think-tool .tool-args { color: var(--fg-muted); }
  .think-tool .tool-result {
    margin-top: 5px; padding-top: 5px; border-top: 1px dotted var(--border);
    color: var(--fg); white-space: pre-wrap; word-break: break-word;
    max-height: 150px; overflow-y: auto;
  }

  .composer {
    padding: 14px 32px; background: var(--bg-elev); border-top: 1px solid var(--border);
    max-width: 1100px; width: 100%; margin: 0 auto;
  }
  .composer-inner { display: flex; gap: 10px; align-items: flex-end; }
  .composer textarea {
    flex: 1; background: var(--bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 12px; font-family: inherit; font-size: 14px; line-height: 1.5;
    min-height: 44px; max-height: 200px; resize: vertical;
  }
  .composer textarea:focus { outline: none; border-color: var(--accent); }
  .composer button {
    padding: 10px 20px; background: var(--accent); color: white;
    border: none; border-radius: 8px; font-weight: 600; cursor: pointer;
    font-size: 14px;
  }
  .composer button:hover { background: #1f6feb; }
  .composer button:disabled { background: var(--border); cursor: not-allowed; }
  .composer .hint { font-size: 11px; color: var(--fg-muted); margin-top: 6px; }

  .empty { text-align: center; color: var(--fg-muted); padding: 80px 20px; }
</style>
</head>
<body>

<div class="header">
  <h1>💬 Hello-Agent Chat</h1>
  <div class="header-actions">
    <a id="viewerLink" href="/">📊 Trace Viewer</a>
    <button onclick="newSession()" style="background:var(--bg-elev2);color:var(--fg);border:1px solid var(--border);padding:5px 12px;border-radius:6px;cursor:pointer;font-size:13px;">🆕 新会话</button>
  </div>
</div>

<div class="settings">
  <label>Session: <input id="sessionInput" type="text" placeholder="auto-generated"></label>
  <label><input type="checkbox" id="useMcp"> Use MCP</label>
  <label><input type="checkbox" id="useMemory"> Use Memory</label>
  <button onclick="clearHistory()" title="只清空当前 session 的聊天历史(不换 session)">🧹 清空历史</button>
  <span style="margin-left:auto;color:var(--fg-muted);font-size:11px;">trace 永远开 · 每轮一个独立 jsonl</span>
</div>

<div class="messages" id="chatLog">
  <div class="empty">输入下方提示词开始聊天。<br><br>每轮 chat 会写入 <code>traces/&lt;session&gt;-NNN.jsonl</code>,可在右上角的 Trace Viewer 实时查看 call flow。</div>
</div>

<div class="composer">
  <div class="composer-inner">
    <textarea id="prompt" placeholder="问点什么…(Enter 提交,Shift+Enter 换行)"></textarea>
    <button id="sendBtn" onclick="send()">发送 ▶</button>
  </div>
  <div class="hint" id="hintLine">就绪</div>
</div>

<script>
// 优先级:URL ?new=1 > URL ?session=xxx > localStorage > random
const _params = new URLSearchParams(location.search);
let sessionBase;
if (_params.get('new') === '1') {
  sessionBase = 'web-' + Math.random().toString(36).slice(2, 8);
  localStorage.removeItem('chatHistory-' + sessionBase);
  localStorage.setItem('chatTurn-' + sessionBase, '0');
  history.replaceState({}, '', '/chat');
} else if (_params.get('session')) {
  sessionBase = _params.get('session');
  history.replaceState({}, '', '/chat');
} else {
  sessionBase = localStorage.getItem('chatSession')
              || ('web-' + Math.random().toString(36).slice(2, 8));
}
localStorage.setItem('chatSession', sessionBase);
let turn = parseInt(localStorage.getItem('chatTurn-' + sessionBase) || '0', 10);
document.getElementById('sessionInput').value = sessionBase;

function updateViewerLink() {
  const link = document.getElementById('viewerLink');
  if (link) link.href = '/?session=' + encodeURIComponent(sessionBase);
}
updateViewerLink();

function escapeHtml(text) {
  // 同 trace viewer:剥 ANSI / 控制字符,再 HTML 转义
  let s = String(text == null ? '' : text)
    .replace(/\x1b\[[\d;]*[A-Za-z]/g, '')
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function renderMarkdownLite(text) {
  // 极简 markdown:**bold**, `code`, ```code blocks```
  let html = escapeHtml(text);
  html = html.replace(/```([\s\S]*?)```/g, (_, code) => `<pre>${code}</pre>`);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  return html;
}

function renderThinkingBlock(steps, totalTokens, elapsedS) {
  if (!steps || !steps.length) return '';
  const parts = steps.map(s => {
    const head = `<div class="think-step-head"><span class="badge">Step ${s.step}</span>`
               + (s.tokens ? `${s.tokens} tok` : '')
               + (s.llm_latency_s ? ` · ${(+s.llm_latency_s).toFixed(2)}s` : '')
               + `</div>`;
    const thoughtHtml = s.thought
      ? `<div class="think-thought">${escapeHtml(s.thought)}</div>`
      : '';
    let toolHtml = '';
    if (s.tool && s.tool.name) {
      const args = s.tool.arguments;
      const argsStr = (args && typeof args === 'object')
        ? JSON.stringify(args)
        : String(args || '');
      toolHtml = `
        <div class="think-tool ${s.tool.is_error ? 'is-error' : ''}">
          <span class="tool-name">🔧 ${escapeHtml(s.tool.name)}</span><span class="tool-args">(${escapeHtml(argsStr)})</span>
          ${s.tool.latency_s ? `<span style="float:right;color:var(--fg-muted);">${(+s.tool.latency_s).toFixed(2)}s</span>` : ''}
          <div class="tool-result">${escapeHtml(s.tool.result || '(empty)')}</div>
        </div>
      `;
    }
    return `<div class="think-step">${head}${thoughtHtml}${toolHtml}</div>`;
  }).join('');
  const summary = `💭 思考过程 · ${steps.length} 步`
                + (totalTokens ? ` · ${totalTokens} tok` : '')
                + (elapsedS ? ` · ${(+elapsedS).toFixed(1)}s` : '')
                + `<span style="margin-left:auto;font-size:10px;">点击展开/折叠</span>`;
  return `<details class="thinking"><summary>${summary}</summary><div class="thinking-body">${parts}</div></details>`;
}

// 全局 chatMessages 数组(结构化),作为 localStorage 持久化的真相源。
// 注意:容器 id 用 chatLog(不用 messages),避免 window.messages 自动属性冲突。
let chatMessages = [];

function appendMsg(msg) {
  // msg = { role, content, meta?, steps?, totalTokens?, elapsedS?, traceSession? }
  const wrap = document.getElementById('chatLog');
  if (!wrap) {
    console.error('appendMsg: #messages container not found');
    return null;
  }
  const empty = wrap.querySelector('.empty');
  if (empty) empty.remove();

  const role = (msg && msg.role) || 'agent';
  const el = document.createElement('div');
  el.className = 'msg ' + role;
  const avatar = role === 'user' ? 'U' : (role === 'error' ? '!' : 'A');
  if (role === 'error') el.classList.add('msg-error');

  let thinkingHtml = '';
  try {
    thinkingHtml = (role === 'agent')
      ? renderThinkingBlock(msg.steps, msg.totalTokens, msg.elapsedS)
      : '';
  } catch (e) {
    console.error('renderThinkingBlock failed:', e, msg);
  }

  let metaHtml = '';
  if (msg.traceSession) {
    metaHtml = `<div class="msg-meta">`
             + (msg.elapsedS ? `⏱ ${(+msg.elapsedS).toFixed(1)}s · ` : '')
             + `<a href="/?trace=${encodeURIComponent(msg.traceSession)}">📊 trace: ${escapeHtml(msg.traceSession)}</a>`
             + `</div>`;
  }

  let contentHtml = '';
  try {
    contentHtml = renderMarkdownLite(msg.content);
  } catch (e) {
    console.error('renderMarkdownLite failed:', e, msg);
    contentHtml = escapeHtml(String(msg.content == null ? '' : msg.content));
  }

  el.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-body">
      <div class="msg-role">${role === 'user' ? 'You' : (role === 'error' ? 'Error' : 'Agent')}</div>
      ${thinkingHtml}
      <div class="msg-content">${contentHtml}</div>
      ${metaHtml}
    </div>
  `;
  wrap.appendChild(el);
  wrap.scrollTop = wrap.scrollHeight;
  return el;
}

function clearHistory() {
  if (!confirm('清空当前 session 的聊天历史?(不会换 session,trace 文件保留)')) return;
  chatMessages = [];
  localStorage.removeItem('chatHistory-' + sessionBase);
  document.getElementById('chatLog').innerHTML = '<div class="empty">历史已清空。继续输入开始新对话。</div>';
}

function newSession() {
  if (!confirm('开始新会话?当前历史只在本浏览器记录,各会话历史独立保存。')) return;
  sessionBase = 'web-' + Math.random().toString(36).slice(2, 8);
  turn = 0;
  chatMessages = [];
  localStorage.setItem('chatSession', sessionBase);
  localStorage.setItem('chatTurn-' + sessionBase, '0');
  localStorage.setItem('chatHistory-' + sessionBase, '[]');
  document.getElementById('sessionInput').value = sessionBase;
  document.getElementById('chatLog').innerHTML = '<div class="empty">新会话 <code>' + sessionBase + '</code> 已开。</div>';
  updateViewerLink();
}

document.getElementById('sessionInput').addEventListener('change', (e) => {
  sessionBase = e.target.value.trim() || sessionBase;
  turn = parseInt(localStorage.getItem('chatTurn-' + sessionBase) || '0', 10);
  localStorage.setItem('chatSession', sessionBase);
  updateViewerLink();
  loadHistory();
  resumePendingIfAny();
});

function loadHistory() {
  chatMessages = [];
  const raw = localStorage.getItem('chatHistory-' + sessionBase);
  const wrap = document.getElementById('chatLog');
  wrap.innerHTML = '';
  if (!raw) return;
  try {
    const history = JSON.parse(raw);
    if (!Array.isArray(history)) {
      console.warn('chatHistory not array, resetting');
      localStorage.removeItem('chatHistory-' + sessionBase);
      return;
    }
    for (const m of history) {
      if (!m || typeof m !== 'object') continue;
      chatMessages.push(m);
      try { appendMsg(m); }
      catch (err) { console.error('appendMsg failed for history item:', err, m); }
    }
  } catch (e) {
    console.error('loadHistory parse error:', e);
    localStorage.removeItem('chatHistory-' + sessionBase);
  }
}

function saveHistory() {
  try {
    localStorage.setItem('chatHistory-' + sessionBase, JSON.stringify(chatMessages));
  } catch (e) {
    console.error('saveHistory error:', e);
  }
}

// 显示一个临时占位 agent 气泡(thinking…),返回 dom 节点供后续移除
function showPendingBubble() {
  const wrap = document.getElementById('chatLog');
  if (!wrap) return null;
  const empty = wrap.querySelector('.empty');
  if (empty) empty.remove();
  const el = document.createElement('div');
  el.className = 'msg agent pending';
  el.id = 'pendingBubble';
  el.innerHTML = `
    <div class="msg-avatar">A</div>
    <div class="msg-body">
      <div class="msg-role">Agent</div>
      <div class="msg-content"><span class="typing">🤔 thinking… <span id="pendingTimer"></span></span></div>
    </div>
  `;
  wrap.appendChild(el);
  wrap.scrollTop = wrap.scrollHeight;
  return el;
}
function removePendingBubble() {
  const el = document.getElementById('pendingBubble');
  if (el) el.remove();
}

async function send() {
  const ta = document.getElementById('prompt');
  const text = ta.value.trim();
  if (!text) return;
  const sendBtn = document.getElementById('sendBtn');
  const hint = document.getElementById('hintLine');

  sendBtn.disabled = true;
  const userMsg = { role: 'user', content: text };
  chatMessages.push(userMsg);
  appendMsg(userMsg);
  ta.value = '';
  hint.textContent = '🤔 thinking…';
  saveHistory();

  // 占位 agent 气泡 + 计时器(直到响应到达才移除)
  showPendingBubble();
  const t0 = performance.now();
  const wallT0 = Date.now();
  const timerInterval = setInterval(() => {
    const t = document.getElementById('pendingTimer');
    if (t) t.textContent = `(${((performance.now() - t0) / 1000).toFixed(1)}s)`;
  }, 200);

  turn += 1;
  localStorage.setItem('chatTurn-' + sessionBase, String(turn));

  // 计算 server 端会写入的 trace_session 名(与 server 内 _run_agent_blocking 保持一致)
  const traceSession = sessionBase + '-' + String(turn).padStart(3, '0');
  // 立刻把 pending 状态持久化:即便用户切走 chat 页 / 关浏览器,
  // 重新进 chat 时可以通过轮询 /api/chat/result/<traceSession> 恢复结果
  localStorage.setItem('chatPending-' + sessionBase, JSON.stringify({
    turn, prompt: text, traceSession, t0: wallT0,
  }));

  const useMcp = document.getElementById('useMcp').checked;
  const useMemory = document.getElementById('useMemory').checked;

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: text,
        session: sessionBase,
        turn: turn,
        use_mcp: useMcp,
        use_memory: useMemory,
      }),
    });
    const data = await resp.json();
    const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
    console.log('[chat] status=' + resp.status + ' elapsed=' + elapsed + 's', data);
    removePendingBubble();

    if (!resp.ok) {
      const errMsg = { role: 'error', content: data.error || `HTTP ${resp.status}` };
      chatMessages.push(errMsg);
      appendMsg(errMsg);
    } else {
      const agentMsg = {
        role: 'agent',
        content: data.answer || '(empty)',
        steps: data.steps || [],
        totalTokens: data.total_tokens || 0,
        elapsedS: data.elapsed_s || +elapsed,
        traceSession: data.trace_session,
      };
      console.log('[chat] received:', agentMsg);
      chatMessages.push(agentMsg);
      appendMsg(agentMsg);
    }
  } catch (e) {
    console.error('[chat] send error:', e);
    removePendingBubble();
    const errMsg = { role: 'error', content: String(e) };
    chatMessages.push(errMsg);
    appendMsg(errMsg);
  } finally {
    clearInterval(timerInterval);
    removePendingBubble();
    localStorage.removeItem('chatPending-' + sessionBase);
    sendBtn.disabled = false;
    hint.textContent = '就绪';
    saveHistory();
    ta.focus();
  }
}

document.getElementById('prompt').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

// 切走再切回时,如果 chatPending-<session> 存在,继续轮询那个 trace_session 的 result
async function resumePendingIfAny() {
  const raw = localStorage.getItem('chatPending-' + sessionBase);
  if (!raw) return;
  let p;
  try { p = JSON.parse(raw); }
  catch (e) { localStorage.removeItem('chatPending-' + sessionBase); return; }
  if (!p || !p.traceSession) {
    localStorage.removeItem('chatPending-' + sessionBase);
    return;
  }
  console.log('[chat] resuming pending request:', p);

  const sendBtn = document.getElementById('sendBtn');
  const hint = document.getElementById('hintLine');
  if (sendBtn) sendBtn.disabled = true;
  if (hint) hint.textContent = '🤔 恢复等待之前发出的请求…';

  showPendingBubble();
  const tStart = p.t0 || Date.now();
  const timerInterval = setInterval(() => {
    const t = document.getElementById('pendingTimer');
    if (t) t.textContent = `(${((Date.now() - tStart) / 1000).toFixed(1)}s · 已恢复)`;
  }, 200);

  const maxWait = 5 * 60 * 1000;  // 5 分钟内还没出 run_end 就当超时
  let result = null;
  while (Date.now() - tStart < maxWait) {
    try {
      const r = await fetch('/api/chat/result/' + encodeURIComponent(p.traceSession));
      if (r.ok) {
        const data = await r.json();
        if (data.status === 'done') { result = data; break; }
      }
    } catch (e) {
      console.warn('[chat] poll error:', e);
    }
    await new Promise(res => setTimeout(res, 1500));
  }

  clearInterval(timerInterval);
  removePendingBubble();

  if (result) {
    const elapsed = (Date.now() - tStart) / 1000;
    const agentMsg = {
      role: 'agent',
      content: result.answer || '(empty)',
      steps: result.steps || [],
      totalTokens: result.total_tokens || 0,
      elapsedS: result.elapsed_s || elapsed,
      traceSession: result.trace_session || p.traceSession,
    };
    chatMessages.push(agentMsg);
    appendMsg(agentMsg);
    saveHistory();
  } else {
    const errMsg = { role: 'error', content: '恢复 pending 请求超时(>5min);agent 可能已完成,请刷新页面或查看 trace。' };
    chatMessages.push(errMsg);
    appendMsg(errMsg);
    saveHistory();
  }
  localStorage.removeItem('chatPending-' + sessionBase);
  if (sendBtn) sendBtn.disabled = false;
  if (hint) hint.textContent = '就绪';
}

loadHistory();
resumePendingIfAny();
document.getElementById('prompt').focus();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Starlette(
    debug=False,
    routes=[
        Route("/", index),
        Route("/chat", chat_index),
        Route("/api/traces", list_traces),
        Route("/api/traces/{name}", get_trace),
        Route("/api/chat", post_chat, methods=["POST"]),
        Route("/api/chat/result/{trace_session}", get_chat_result),
    ],
)


def _ensure_utf8_stdout() -> None:
    import sys

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def main() -> None:
    _ensure_utf8_stdout()
    port = int(os.getenv("TRACE_PORT", "8088"))
    host = os.getenv("TRACE_HOST", "127.0.0.1")
    print(f"\n  Trace Viewer running at http://{host}:{port}\n")
    print(f"     traces dir: {TRACES_DIR.resolve()}")
    print(f"     to stop: Ctrl+C\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
