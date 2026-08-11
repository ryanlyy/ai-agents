"""T01: M1 L3 add(a,b) 完整 function calling

直接抄课程文档 M1 L3 第 5 题"编程"参考答案,只把 model 走 env (Ollama gpt-oss:20b).
"""
from _env import banner, ok, fail, API_KEY, BASE_URL, MODEL
from openai import OpenAI
import json

banner("M1 L3 编程题 — add(a,b) 完整 tool calling")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def add(a: float, b: float) -> float:
    return a + b

tools = [{
    "type": "function",
    "function": {
        "name": "add",
        "description": "Add two numbers a and b and return the sum. Use this whenever the user asks for arithmetic addition. Do NOT use for subtraction/multiplication/division.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "first addend"},
                "b": {"type": "number", "description": "second addend"},
            },
            "required": ["a", "b"],
        },
    },
}]

messages = [{"role": "user", "content": "13.5 加 27.8 是多少?用工具算,不要心算。"}]
resp1 = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
msg = resp1.choices[0].message
messages.append(msg)

if not msg.tool_calls:
    fail(f"模型没调工具,直接答了:{msg.content[:200]}")

print(f"  模型决定调 {len(msg.tool_calls)} 个工具")
for call in msg.tool_calls:
    print(f"    → {call.function.name}({call.function.arguments})")
    args   = json.loads(call.function.arguments)
    result = add(**args)
    messages.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})

resp2 = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
final = resp2.choices[0].message.content
print(f"  最终回复: {final}")

if final and ("41.3" in final or "41.30" in final):
    ok("add(a,b) 端到端跑通,结果含 41.3")
else:
    fail(f"最终回复未含正确值 41.3:{final!r}")
