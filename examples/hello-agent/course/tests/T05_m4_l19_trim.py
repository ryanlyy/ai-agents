"""T05: M4 L19 trim_with_summary 逻辑

抄课程文档 M4 L19 的 trim_with_summary 实现.
本测试不真调 LLM 摘要(避免慢),只测窗口裁剪逻辑.
"""
from _env import banner, ok, fail

banner("M4 L19 — trim_with_summary 窗口裁剪逻辑")

def trim_with_summary(messages, max_recent=6, summarize_fn=None):
    """保留 system + (摘要) + 最近 max_recent 条 non-system."""
    system = [m for m in messages if m["role"] == "system"]
    others = [m for m in messages if m["role"] != "system"]
    if len(others) <= 2 * max_recent:
        return system + others
    cut    = len(others) - max_recent
    older  = others[:cut]
    recent = others[cut:]
    summary_text = summarize_fn(older) if summarize_fn else f"[摘要] 早期 {len(older)} 条已折叠"
    summary_msg  = {"role": "system", "content": summary_text}
    return system + [summary_msg] + recent

msgs = [{"role": "system", "content": "你是助手"}]
for i in range(20):
    role = "user" if i % 2 == 0 else "assistant"
    msgs.append({"role": role, "content": f"消息 {i}"})

trimmed = trim_with_summary(msgs, max_recent=6, summarize_fn=lambda ms: f"[摘要] 折叠 {len(ms)} 条")

# 验收
assert trimmed[0]["role"] == "system" and trimmed[0]["content"] == "你是助手", "system 必须保留"
assert "[摘要]" in trimmed[1]["content"], "应有摘要 system message"
assert len(trimmed) == 1 + 1 + 6, f"长度应为 8, 实际 {len(trimmed)}: {[m['content'] for m in trimmed]}"
assert trimmed[-1]["content"] == "消息 19", "最后一条应是消息 19"
print(f"  原始 {len(msgs)} 条 -> 裁剪后 {len(trimmed)} 条:")
for m in trimmed:
    print(f"    [{m['role']:9}] {m['content'][:50]}")

ok("trim_with_summary 正确保留 system + 摘要 + 最近 6 条")
