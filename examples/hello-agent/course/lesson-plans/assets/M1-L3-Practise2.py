from openai import OpenAI
import json, os
from dotenv import load_dotenv
load_dotenv()

api_key  = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL") or None       # 空字符串当作 None,SDK 用默认端点
assert api_key, "未读到 OPENAI_API_KEY——请检查 .env 文件名/位置/变量名"

client = OpenAI(api_key=api_key, base_url=base_url)
MODEL  = os.getenv("OPENAI_MODEL", "gpt-4.1")          # 用国内兼容服务时改 .env 即可,无需改代码

tools = [{
    "type": "function",
    "function": {
        "name": "add",
        "description": (
            "Add two numbers and return their sum. "
            "Use this whenever the user asks an arithmetic addition question "
            "(e.g. '3 加 5'、'what is 12 + 7'). "
            "Do NOT use this for subtraction, multiplication, or division."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "the first addend"},
                "b": {"type": "number", "description": "the second addend"}
            },
            "required": ["a", "b"]
        }
    }
}]

def add(a, b):
    return a + b

messages = [{"role": "user", "content": "3 加 5 等于几?"}]

resp = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
msg = resp.choices[0].message
assert msg.tool_calls, "模型没调工具——回去改 description!"

messages.append(msg)                                  # ① assistant 先入
for call in msg.tool_calls:
    args = json.loads(call.function.arguments)        # ② JSON 字符串
    result = add(**args)
    messages.append({                                  # ③ role=tool + tool_call_id
        "role": "tool",
        "tool_call_id": call.id,
        "content": str(result)
    })

resp2 = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
print(resp2.choices[0].message.content)
# 预期输出形如:"3 加 5 等于 8。"
