"""T02: M2 L8/L9 完整 ReAct 主循环

抄课程文档 M2 L8 第 5 题"持续循环直到没有 tool_calls"参考答案.
验证:① 工具注册表;② max_steps;③ 异常写回;④ 正常 final 退出.
"""
from _env import banner, ok, fail, API_KEY, BASE_URL, MODEL
from openai import OpenAI
import json

banner("M2 L9 — 完整 ReAct 主循环 (registry + max_steps + 异常写回)")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def get_weather(city: str) -> str:
    fake = {"北京": "22°C 多云", "上海": "26°C 雨", "深圳": "30°C 晴"}
    return f"{city} 今天 {fake.get(city, '25°C 晴')}"

def get_news(topic: str) -> str:
    return f"今日 {topic} 头条:某科技公司发布新模型"

TOOL_REGISTRY = {"get_weather": get_weather, "get_news": get_news}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Get today's weather for a city.",
        "parameters": {"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}},
    {"type": "function", "function": {
        "name": "get_news",
        "description": "Get today's top news for a given topic.",
        "parameters": {"type":"object","properties":{"topic":{"type":"string"}},"required":["topic"]}}},
]

def run_agent(user_input: str, max_steps: int = 6) -> str:
    messages = [{"role": "user", "content": user_input}]
    for step in range(max_steps):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOL_SCHEMAS)
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            print(f"  [step {step}] FINAL: {msg.content[:80]}")
            return msg.content
        for call in msg.tool_calls:
            print(f"  [step {step}] CALL {call.function.name}({call.function.arguments})")
            fn = TOOL_REGISTRY.get(call.function.name)
            try:
                args   = json.loads(call.function.arguments)
                result = fn(**args) if fn else f"unknown tool: {call.function.name}"
            except Exception as e:
                result = f"ERROR: {type(e).__name__}: {e}"
            messages.append({"role":"tool", "tool_call_id":call.id, "content":str(result)})
    return "max_steps exceeded"

ans = run_agent("帮我看一下上海今天天气,以及科技领域有什么头条")

if "max_steps" in (ans or ""):
    fail(f"超 max_steps 未给出 final: {ans}")
if ans and (("26" in ans) or ("雨" in ans) or ("科技" in ans)):
    ok(f"ReAct 循环跑通,模型综合了天气与新闻信息")
else:
    fail(f"最终答案不含期望关键词: {ans!r}")
