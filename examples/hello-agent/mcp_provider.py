"""
把 MCP Server(异步、stdio 子进程)封装成同步接口,让现有的 sync Agent 可以直接用。

实现思路:
  - 启动一个独立线程跑 asyncio event loop。
  - 在那里建立 MCP stdio 子进程 + ClientSession,并保持长连接。
  - 主线程调用同步方法时,通过 run_coroutine_threadsafe 调度到 loop。
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict


class MCPProvider:
    """以同步 API 的方式,接入一个用 stdio 启动的 MCP Server。"""

    def __init__(self, command: str, args: list[str], tracer=None):
        self.command = command
        self.args = args
        self._tracer = tracer
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="mcp-loop", daemon=True
        )
        self._thread.start()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[MCPTool] = []
        self._connect()
        if self._tracer is not None:
            self._tracer.log(
                "mcp_initialize",
                {
                    "command": command,
                    "args": args,
                    "tools": [t.name for t in self._tools],
                },
            )

    # ------------------------------------------------------------------
    # 公共同步 API
    # ------------------------------------------------------------------

    def list_tools(self) -> list[MCPTool]:
        return self._tools

    def list_tools_openai_format(self) -> list[dict]:
        """把 MCP 工具描述转成 OpenAI Function Calling 期望的格式。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema or {"type": "object", "properties": {}},
                },
            }
            for t in self._tools
        ]

    def call_tool(self, name: str, arguments: dict) -> str:
        if self._tracer is not None:
            self._tracer.log(
                "mcp_request",
                {"method": "tools/call", "name": name, "arguments": arguments},
            )
        t0 = time.perf_counter()
        result = self._submit(self._call_tool(name, arguments))
        latency = time.perf_counter() - t0
        if self._tracer is not None:
            preview = result if len(result) <= 1000 else result[:1000] + "…"
            self._tracer.log(
                "mcp_response",
                {
                    "method": "tools/call",
                    "name": name,
                    "latency_s": round(latency, 4),
                    "result_preview": preview,
                },
            )
        return result

    def close(self) -> None:
        try:
            self._submit(self._close())
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _submit(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def _connect(self) -> None:
        self._submit(self._setup())

    async def _setup(self) -> None:
        self._stack = AsyncExitStack()
        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=None,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        result = await self._session.list_tools()
        self._tools = [
            MCPTool(
                name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema or {},
            )
            for t in result.tools
        ]

    async def _call_tool(self, name: str, arguments: dict) -> str:
        assert self._session is not None
        result = await self._session.call_tool(name, arguments=arguments)
        # 把 content blocks 拼成单个字符串返回
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(str(block))
        if result.isError:
            return "错误:" + ("\n".join(parts) or "(MCP 工具返回了错误,但无文本)")
        return "\n".join(parts)

    async def _close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None


def build_default_provider(tracer=None) -> MCPProvider:
    """用当前 venv 的 Python 拉起本仓库的 mcp_server.py。"""
    return MCPProvider(command=sys.executable, args=["mcp_server.py"], tracer=tracer)
