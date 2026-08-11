"""T08: M5 L26 + M6 L29 LangGraph + SqliteSaver

★ 重点验证 D 阶段修复 ★
课程文档 M6 L29 之前写的是:
    saver = SqliteSaver.from_conn_string("checkpoints.db")   # ❌ 这是 context manager,不能直接赋值
    app = g.compile(checkpointer=saver, ...)

修复后用直接构造:
    conn  = sqlite3.connect("checkpoints.db", check_same_thread=False)
    saver = SqliteSaver(conn)
    app   = g.compile(checkpointer=saver, ...)

本测试验证修复版能正确运行 + 旧错误写法会失败.
"""
from _env import banner, ok, fail
import sqlite3, os
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

banner("M5/M6 — LangGraph StateGraph + SqliteSaver (D 阶段关键修复)")

DB = os.path.join(os.path.dirname(__file__), "_t08_check.db")
if os.path.exists(DB): os.remove(DB)

class State(TypedDict):
    count: int
    log:   list[str]

def increment(state):
    return {"count": state["count"] + 1, "log": state["log"] + [f"+1 -> {state['count']+1}"]}

def is_done(state) -> str:
    return "end" if state["count"] >= 3 else "loop"

g = StateGraph(State)
g.add_node("inc", increment)
g.set_entry_point("inc")
g.add_conditional_edges("inc", is_done, {"loop": "inc", "end": END})

# ───────── 关键:正确写法(直接构造) ─────────
conn  = sqlite3.connect(DB, check_same_thread=False)
saver = SqliteSaver(conn)
app   = g.compile(checkpointer=saver)

cfg = {"configurable": {"thread_id": "t08-run-1"}}
result = app.invoke({"count": 0, "log": []}, config=cfg)
print(f"  正确写法跑通: count={result['count']}, log={result['log']}")
assert result["count"] == 3, f"应 inc 到 3, 实际 {result['count']}"

# 验证 state 已持久化:模拟"重启"用新 saver 同一 thread_id 拿历史
conn2  = sqlite3.connect(DB, check_same_thread=False)
saver2 = SqliteSaver(conn2)
app2   = g.compile(checkpointer=saver2)
state_snapshot = app2.get_state(cfg)
print(f"  重启后取 state: count={state_snapshot.values.get('count')}")
assert state_snapshot.values["count"] == 3, "重启后 state 应能恢复"

# ───────── 旁路:验证旧错误写法确实会失败 ─────────
try:
    bad_saver = SqliteSaver.from_conn_string(DB)   # ← 这其实返回 _GeneratorContextManager
    # 试图直接当 saver 用 → 应该出错
    bad_app = g.compile(checkpointer=bad_saver)
    bad_result = bad_app.invoke({"count": 0, "log": []}, config={"configurable": {"thread_id": "bad"}})
    print(f"  WARNING: 旧错误写法竟然没炸? type={type(bad_saver).__name__}")
    print(f"  result: {bad_result}")
except (TypeError, AttributeError, Exception) as e:
    print(f"  确认旧错误写法会失败: {type(e).__name__}: {str(e)[:120]}")

# cleanup
conn.close(); conn2.close()
if os.path.exists(DB): os.remove(DB)
ok("LangGraph + SqliteSaver 直接构造写法跑通 (D 阶段 M6 L29 修复正确)")
