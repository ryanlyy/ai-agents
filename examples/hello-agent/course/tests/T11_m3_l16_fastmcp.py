"""T11: M3 L16 FastMCP server 声明

抄课程文档 M3 L15 第 6 题作业 + L16 演示的 FastMCP server 写法.
不实际启动 stdio 服务器(要外部 inspector 连接), 只验证装饰器把 tool/resource/prompt
正确注册到 mcp 实例上.
"""
from _env import banner, ok, fail
from fastmcp import FastMCP

banner("M3 L15/L16 — FastMCP server tool / resource / prompt 注册")

mcp = FastMCP("test-server")

@mcp.tool()
def add(a: float, b: float) -> str:
    """Add two numbers a and b."""
    return str(a + b)

@mcp.tool()
def divide(a: float, b: float) -> str:
    """Divide a by b. Returns error if b is zero."""
    if b == 0:
        return "ERROR: division by zero"
    return str(a / b)

@mcp.resource("kb://policy/refund")
def refund_policy() -> str:
    """退款政策全文."""
    return "1. 收货 7 天内无理由退款\n2. 拆封后只能换不能退"

@mcp.prompt()
def handle_complaint(customer_msg: str, order_id: str) -> list[dict]:
    """生成处理客户投诉的对话模板."""
    return [
        {"role": "system",  "content": "你是一名资深客服."},
        {"role": "user",    "content": f"订单 {order_id} 投诉: {customer_msg}"},
    ]

# 验证已注册——FastMCP 3.x 用 _list_*() 内部 API 列出, 用 call_tool/get_resource/get_prompt 行为验证
import asyncio
async def check():
    tools     = await mcp._list_tools()
    resources = await mcp._list_resources()
    prompts   = await mcp._list_prompts()
    return tools, resources, prompts

tools, resources, prompts = asyncio.run(check())

tool_names    = [t.name for t in tools]
res_uris      = [str(r.uri) for r in resources]
prompt_names  = [p.name for p in prompts]

print(f"  注册 tools:     {tool_names}")
print(f"  注册 resources: {res_uris}")
print(f"  注册 prompts:   {prompt_names}")

assert "add" in tool_names and "divide" in tool_names, f"add/divide 应注册: {tool_names}"
assert any("refund" in u for u in res_uris), f"refund policy 应注册: {res_uris}"
assert "handle_complaint" in prompt_names, f"handle_complaint 应注册: {prompt_names}"

# 行为测试 1:add(1.5, 2.5) → 4.0
async def call_add():
    r = await mcp._call_tool_mcp("add", {"a": 1.5, "b": 2.5})
    return r

res = asyncio.run(call_add())
add_text = res.content[0].text if (res.content and hasattr(res.content[0], 'text')) else str(res)
print(f"  add(1.5, 2.5) -> {add_text}")
assert "4" in add_text, f"add 结果应含 4.0: {add_text}"

# 行为测试 2:divide(10, 0) → 含 ERROR
async def call_div():
    return await mcp._call_tool_mcp("divide", {"a": 10, "b": 0})
res = asyncio.run(call_div())
div_text = res.content[0].text if (res.content and hasattr(res.content[0], 'text')) else str(res)
print(f"  divide(10, 0) -> {div_text}")
assert ("ERROR" in div_text) or ("zero" in div_text.lower()), f"应返 ERROR: {div_text}"

ok("FastMCP @mcp.tool/@mcp.resource/@mcp.prompt 装饰器全部正确注册 + 行为正确")
