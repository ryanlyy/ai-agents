"""
工具实现层。

每个工具:
  1. 是一个普通 Python 函数,签名清晰、有 docstring。
  2. 在 TOOL_SCHEMAS 中注册成 OpenAI Function Calling 格式。
  3. 返回**字符串**(便于直接回填给 LLM);出错时也返回字符串错误信息,而不是抛异常。

把工具单独放一个文件,是为了 Step 4 可以平滑迁移到 MCP Server。

进阶:research_topic 是个 "Agent-as-Tool" — 工具内部包装一个 multi-agent 系统。
通过 set_tracer() 接收 outer agent 的 tracer,让内部 supervisor/worker/synthesizer
的所有 LLM 调用都进入同一个 trace,便于在浏览器里看完整 call flow。
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# 模块级 tracer 注入点(供 agent.py 启动时调用)
# ---------------------------------------------------------------------------

_current_tracer = None


def set_tracer(tracer) -> None:
    """注入 outer agent 的 tracer。被 research_topic 这类 meta-tool 透传到内部 agent。"""
    global _current_tracer
    _current_tracer = tracer


def get_current_time(timezone: str = "UTC") -> str:
    """返回指定时区的当前时间。timezone 形如 'UTC' / 'Asia/Shanghai' / 'America/New_York'。"""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return f"错误:未知时区 '{timezone}'。请使用 IANA 时区名,例如 'Asia/Shanghai'。"
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def calculate(expression: str) -> str:
    """安全地计算数学表达式。支持 +-*/、**、sqrt、log、sin、cos、pi、e 等。"""
    allowed_names = {
        "sqrt": math.sqrt,
        "log": math.log,
        "log2": math.log2,
        "log10": math.log10,
        "exp": math.exp,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "pi": math.pi,
        "e": math.e,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pow": pow,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
    except Exception as exc:
        return f"错误:无法计算表达式 '{expression}': {exc}"
    return str(result)


def list_files(path: str = ".", pattern: str = "*") -> str:
    """列出目录下匹配 pattern 的文件。pattern 是 glob,例如 '*.md'、'**/*.py'。"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"错误:路径不存在 '{path}'"
    if not p.is_dir():
        return f"错误:'{path}' 不是目录"
    files = sorted(str(f.relative_to(p)) for f in p.glob(pattern) if f.is_file())
    if not files:
        return f"目录 '{path}' 下没有匹配 '{pattern}' 的文件。"
    return "\n".join(files)


def read_file(path: str, max_chars: int = 4000) -> str:
    """读取文本文件内容。超过 max_chars 会截断,避免吃爆上下文。"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"错误:文件不存在 '{path}'"
    if not p.is_file():
        return f"错误:'{path}' 不是文件"
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"错误:文件 '{path}' 不是 UTF-8 文本文件"
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n…(已截断,文件总长 {len(text)} 字符)"
    return text


def word_count(text: str) -> str:
    """统计文本的字符数、单词数、行数。中英文都支持。"""
    chars = len(text)
    words = len(text.split())
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return f"字符数: {chars}, 单词数: {words}, 行数: {lines}"


def write_file(path: str, content: str) -> str:
    """把 content 写入指定路径(已存在则覆盖)。**写操作,需要审批。**"""
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {p}({len(content)} 字符)"


def delete_file(path: str) -> str:
    """删除指定文件。**破坏性操作,需要审批。**"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"错误:文件不存在 '{path}'"
    if not p.is_file():
        return f"错误:'{path}' 不是文件,拒绝删除"
    p.unlink()
    return f"已删除 {p}"


def http_get(url: str, max_chars: int = 4000) -> str:
    """HTTP GET 一个公开 URL,返回 状态码 + content-type + 截断后的正文。

    - 仅支持 http / https,其他 scheme 直接拒绝。
    - 自动跟随重定向(最多 5 次)。
    - 总超时 10s。
    - 大响应自动截断到 max_chars。
    """
    import httpx

    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return f"错误:仅支持 http/https URL,收到 '{str(url)[:80]}'"

    # 如果 outer agent 注入了 tracer,用 traced client,让出公网请求也进 trace
    if _current_tracer is not None:
        from tracing_http import make_traced_client

        client_ctx = make_traced_client(
            _current_tracer, timeout=10.0, follow_redirects=True
        )
    else:
        client_ctx = httpx.Client(timeout=10.0, follow_redirects=True)

    try:
        with client_ctx as client:
            r = client.get(url)
    except httpx.TimeoutException:
        return f"错误:请求超时(10s): {url}"
    except httpx.RequestError as exc:
        return f"错误:请求失败 ({type(exc).__name__}): {exc}"

    ctype = (r.headers.get("content-type") or "unknown").split(";")[0].strip()
    body = r.text
    full_len = len(body)
    truncated_note = ""
    if full_len > max_chars:
        body = body[:max_chars]
        truncated_note = f"; truncated to {max_chars}"
    header = f"HTTP {r.status_code} {ctype} {full_len} bytes{truncated_note}"
    return f"{header}\n{body}"


def research_topic(topic: str, urls: list[str]) -> str:
    """对一个主题在给定 URL 列表上做研究,**内部用 multi-agent 系统协作**。

    工作流(由内部 supervisor 自动调度):
      1. WebWorker 用 http_get 抓每个 URL
      2. (可能)FileWorker / MathWorker 处理细节
      3. Synthesizer 把多个 worker 的产出合成最终回答

    这是经典的 "Agent-as-Tool" 模式 —— outer agent 看到的是一次普通 tool_call,
    实际背后是一整套 supervisor + worker + synthesizer 协作。

    如果 outer 设了 tracer,内部 LLM 调用会进入同一个 trace,call flow 图能看到嵌套层次。
    """
    from agent_multi import MultiAgentSystem, MultiConfig

    if not isinstance(urls, list) or not urls:
        return "错误:需要至少 1 个 URL"

    cfg = MultiConfig(
        model=os.getenv("AGENT_MODEL", "gpt-4.1-mini"),
        max_rounds=4,
    )
    system = MultiAgentSystem(config=cfg, tracer=_current_tracer)

    urls_block = "\n".join(f"- {u}" for u in urls)
    task = (
        f"研究主题:「{topic}」\n\n"
        f"参考 URL:\n{urls_block}\n\n"
        f"请用 http_get 工具抓取这些 URL,综合内容用 1-3 段话回答 topic 相关的核心信息。"
        f"对每个事实标注来源 URL。"
    )
    try:
        return system.run(task)
    except Exception as exc:
        return f"错误:research_topic 内部 multi-agent 失败: {type(exc).__name__}: {exc}"


def file_stats(path: str) -> str:
    """直接基于文件路径统计字符数、单词数、行数、字节数。

    与 word_count 不同,本工具流式读取文件,**不会把内容载入 LLM 上下文**,
    适合统计大文件,不会被 read_file 的截断影响。
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"错误:文件不存在 '{path}'"
    if not p.is_file():
        return f"错误:'{path}' 不是文件"

    size_bytes = p.stat().st_size
    chars = 0
    words = 0
    lines = 0
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                lines += 1
                chars += len(line)
                words += len(line.split())
    except UnicodeDecodeError:
        return f"错误:文件 '{path}' 不是 UTF-8 文本文件(总字节数 {size_bytes})"

    return (
        f"文件: {p.name}\n"
        f"行数: {lines}\n"
        f"字符数: {chars}\n"
        f"单词数: {words}\n"
        f"字节数: {size_bytes}"
    )


# ---------------------------------------------------------------------------
# OpenAI Function Calling 注册表
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "list_files": list_files,
    "read_file": read_file,
    "word_count": word_count,
    "file_stats": file_stats,
    "write_file": write_file,
    "delete_file": delete_file,
    "http_get": http_get,
    "research_topic": research_topic,
}

# Step 7:被列为 "dangerous" 的工具,默认会触发人工审批。
DANGEROUS_TOOLS: set[str] = {"write_file", "delete_file"}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取指定时区的当前时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区名,例如 'UTC'、'Asia/Shanghai'、'America/New_York'。默认 UTC。",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算数学表达式。支持 +-*/、**、sqrt、log、sin、cos、pi、e。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的表达式,例如 '(1+2)*3' 或 'sqrt(2)*100'。",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出目录下匹配 glob 模式的文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径,默认当前目录。"},
                    "pattern": {
                        "type": "string",
                        "description": "glob 模式,例如 '*.md'、'**/*.py'。默认 '*'。",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文本文件内容(自动截断超长文件)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径。"},
                    "max_chars": {
                        "type": "integer",
                        "description": "最大返回字符数,默认 4000。",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "word_count",
            "description": (
                "统计**已经在上下文中**的一段文本的字符数、单词数、行数。"
                "如果你要统计的是磁盘上的文件,请改用 file_stats,避免读全文。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要统计的文本内容。"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_stats",
            "description": (
                "基于文件路径直接统计字符数、单词数、行数、字节数。"
                "**首选用于文件统计任务**,因为它流式读取文件,不会把内容塞进上下文,"
                "也不会被 read_file 的 max_chars 截断影响。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径。"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "写入文件(已存在则覆盖)。**破坏性操作,会触发人工审批,不要随便用。**"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件路径。"},
                    "content": {"type": "string", "description": "要写入的文本内容。"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "删除文件。**破坏性操作,会触发人工审批,不可逆。**"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的文件路径。"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_get",
            "description": (
                "HTTP GET 一个公开 URL,返回状态码、content-type 和正文(自动截断)。"
                "仅支持 http/https,超时 10 秒,自动跟随重定向。"
                "适合抓取网页、调用公开 JSON API。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要请求的完整 URL,必须以 http:// 或 https:// 开头。"},
                    "max_chars": {
                        "type": "integer",
                        "description": "正文截断到的字符数,默认 4000。",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_topic",
            "description": (
                "对一个主题在给定 URL 列表上做研究,内部用 **multi-agent 系统**(Supervisor + WebWorker + Synthesizer)协作。"
                "适合需要从 2 个或以上 URL 综合信息再合成回答的复杂任务。"
                "比直接连续调 http_get 慢但更结构化,内部 LLM 调用会进入同一份 trace。"
                "**慎用**:简单单 URL 抓取请直接用 http_get。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "研究主题,例如 '比较两个 API 的差异'、'抓取并总结这几篇博文的观点'。",
                    },
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URL 列表(必须 ≥1 个),每个都以 http:// 或 https:// 开头。",
                    },
                },
                "required": ["topic", "urls"],
            },
        },
    },
]
