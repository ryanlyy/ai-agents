"""T06: M4 L20 SQLite session 持久化

抄课程文档 M4 L20 第 7 题"agent --resume <session_id>"参考答案的 DB 部分.
验证:写入 messages → 重启进程 → 读回完全一致.
"""
from _env import banner, ok, fail
import sqlite3, uuid, json, os
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "_t06_test.db")
if os.path.exists(DB): os.remove(DB)

banner("M4 L20 — SQLite session 持久化 + resume")

def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript("""
      CREATE TABLE sessions(session_id TEXT PRIMARY KEY, user_id TEXT, created_at TEXT);
      CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT REFERENCES sessions(session_id),
                            role TEXT, content TEXT, tool_call_id TEXT, tool_calls TEXT, created_at TEXT);
    """)
    conn.commit()
    return conn

def save_message(conn, sid, msg):
    conn.execute(
        "INSERT INTO messages(session_id,role,content,tool_call_id,tool_calls,created_at) VALUES (?,?,?,?,?,?)",
        (sid, msg["role"], msg.get("content"), msg.get("tool_call_id"),
         json.dumps(msg.get("tool_calls"), default=str) if msg.get("tool_calls") else None,
         datetime.utcnow().isoformat()))
    conn.commit()

def load_messages(conn, sid):
    rows = conn.execute("SELECT role, content, tool_call_id, tool_calls FROM messages WHERE session_id=? ORDER BY id",
                        (sid,)).fetchall()
    out = []
    for role, content, tcid, tcalls in rows:
        m = {"role": role, "content": content}
        if tcid:   m["tool_call_id"] = tcid
        if tcalls: m["tool_calls"]   = json.loads(tcalls)
        out.append(m)
    return out

# Round 1: 写
conn = init_db()
sid  = uuid.uuid4().hex[:12]
conn.execute("INSERT INTO sessions VALUES (?,?,?)", (sid, "alice", datetime.utcnow().isoformat()))
original = [
    {"role":"system",   "content":"你是助手"},
    {"role":"user",     "content":"你好"},
    {"role":"assistant","content":"我能帮你做什么?"},
    {"role":"user",     "content":"今天上海天气?"},
    {"role":"tool",     "tool_call_id":"call_abc", "content":"26C 雨"},
]
for m in original:
    save_message(conn, sid, m)
conn.close()
print(f"  写入 session_id={sid}, {len(original)} 条 message")

# Round 2: 模拟"重启",新连接读回
conn2 = sqlite3.connect(DB)
restored = load_messages(conn2, sid)
conn2.close()
print(f"  读回 {len(restored)} 条 message")

# 验收
assert len(restored) == len(original), f"长度不匹配: {len(restored)} vs {len(original)}"
for o, r in zip(original, restored):
    for k in ("role","content"):
        assert o[k] == r[k], f"字段 {k} 不匹配: {o[k]!r} vs {r[k]!r}"
    if "tool_call_id" in o:
        assert r.get("tool_call_id") == o["tool_call_id"], "tool_call_id 不一致"

# cleanup
if os.path.exists(DB): os.remove(DB)
ok("session 写入 + 重启读回 5 条消息完全一致 (含 role=tool 的 tool_call_id)")
