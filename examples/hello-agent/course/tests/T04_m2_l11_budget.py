"""T04: M2 L11 预算守卫 BudgetExceeded

抄课程文档 M2 L11 第 7 题"加 MAX_TOTAL_COST 守卫"参考答案.
故意把预算调到 0.0001 USD,确保第 1 步就触发 BudgetExceeded.
"""
from _env import banner, ok, fail, API_KEY, BASE_URL, MODEL
from openai import OpenAI

banner("M2 L11 — BudgetExceeded 预算守卫")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

MAX_TOTAL_COST   = 0.0001
PRICE_PER_1M_IN  = 2.0
PRICE_PER_1M_OUT = 8.0

class BudgetExceeded(Exception): pass

def call_cost(usage) -> float:
    if not usage: return 0.0
    return (usage.prompt_tokens / 1_000_000) * PRICE_PER_1M_IN \
         + (usage.completion_tokens / 1_000_000) * PRICE_PER_1M_OUT

def run_agent(user_input: str, max_steps: int = 5) -> str:
    messages = [{"role":"user","content":user_input}]
    total_cost = 0.0
    for step in range(max_steps):
        resp = client.chat.completions.create(model=MODEL, messages=messages)
        c = call_cost(resp.usage)
        total_cost += c
        print(f"  [step {step}] cost=${c:.6f}  total=${total_cost:.6f}")
        if total_cost > MAX_TOTAL_COST:
            raise BudgetExceeded(
                f"total ${total_cost:.6f} > ${MAX_TOTAL_COST}, step={step}")
        msg = resp.choices[0].message
        messages.append(msg)
        return msg.content   # 简化:1 步就返
    return "max_steps exceeded"

try:
    run_agent("写一段100字的童话故事")
    fail("预算守卫未触发 — total_cost 没超 MAX_TOTAL_COST")
except BudgetExceeded as e:
    ok(f"BudgetExceeded 正确抛出: {e}")
