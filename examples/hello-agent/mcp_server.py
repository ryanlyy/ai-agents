"""
MCP Server:把 hello-agent 的本地工具通过 stdio 暴露成标准 MCP 工具。

任何 MCP 兼容客户端(Cursor / Claude Desktop / 我们自己的 mcp_provider.py)
都可以连接它,而不必再依赖 hello-agent 的 Python 进程。

启动方式(通常由客户端通过 stdio 子进程拉起,不用手工跑):

    python mcp_server.py

调试时可用 MCP Inspector:

    npx @modelcontextprotocol/inspector python mcp_server.py
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools import (
    calculate as _calculate,
    file_stats as _file_stats,
    get_current_time as _get_current_time,
    http_get as _http_get,
    list_files as _list_files,
    read_file as _read_file,
    word_count as _word_count,
)

mcp = FastMCP("hello-agent-tools")


@mcp.tool()
def get_current_time(timezone: str = "UTC") -> str:
    """获取指定时区的当前时间(IANA 时区名,如 'Asia/Shanghai')。"""
    return _get_current_time(timezone)


@mcp.tool()
def calculate(expression: str) -> str:
    """计算数学表达式。支持 +-*/、**、sqrt、log、sin、cos、pi、e。"""
    return _calculate(expression)


@mcp.tool()
def list_files(path: str = ".", pattern: str = "*") -> str:
    """列出目录下匹配 glob 模式的文件,例如 pattern='*.md'。"""
    return _list_files(path, pattern)


@mcp.tool()
def read_file(path: str, max_chars: int = 4000) -> str:
    """读取文本文件内容(自动截断超长文件,默认 4000 字符)。"""
    return _read_file(path, max_chars)


@mcp.tool()
def word_count(text: str) -> str:
    """统计**已经在上下文中**的一段文本的字符数、单词数、行数。
    要统计磁盘文件请用 file_stats。
    """
    return _word_count(text)


@mcp.tool()
def file_stats(path: str) -> str:
    """基于文件路径直接流式统计字符数/单词数/行数/字节数。**首选用于文件统计任务**。"""
    return _file_stats(path)


@mcp.tool()
def http_get(url: str, max_chars: int = 4000) -> str:
    """HTTP GET 一个公开 URL,返回状态码、content-type、截断后的正文。
    仅支持 http/https,超时 10s,自动跟随重定向。
    适合抓网页或调用公开 JSON API。
    """
    return _http_get(url, max_chars)


if __name__ == "__main__":
    mcp.run(transport="stdio")
