"""T10: M7 L33 FastAPI 部署

抄课程文档 M7 L33 第 6 题"接成 FastAPI 同步版"参考答案.
不真启动 uvicorn server (避免端口冲突), 用 TestClient 直接测 endpoint.
"""
from _env import banner, ok, fail
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from typing import Optional
import time

banner("M7 L33 — FastAPI /chat + /health endpoint")

class BudgetExceeded(Exception): pass

def fake_run_agent(user_input: str, max_steps: int = 10) -> str:
    if "贵" in user_input:
        raise BudgetExceeded("total $0.50 > $0.10")
    if "炸" in user_input:
        raise RuntimeError("simulated internal error")
    return f"echo: {user_input}"

app = FastAPI(title="My Agent API")

class ChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=4000)
    max_steps:  int = Field(10, ge=1, le=20)
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer:     str
    elapsed_ms: int
    session_id: Optional[str] = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    t0 = time.time()
    try:
        answer = fake_run_agent(req.user_input, req.max_steps)
    except BudgetExceeded as e:
        raise HTTPException(status_code=402, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"internal: {type(e).__name__}")
    return ChatResponse(answer=answer, elapsed_ms=int((time.time()-t0)*1000), session_id=req.session_id)

# ───────── TestClient 测试 4 条路径 ─────────
client = TestClient(app)

r = client.get("/health")
assert r.status_code == 200 and r.json() == {"status": "ok"}
print(f"  GET  /health           -> {r.status_code} {r.json()}")
ok("/health 返回 200 ok")

r = client.post("/chat", json={"user_input": "你好"})
assert r.status_code == 200, f"应 200, got {r.status_code}: {r.text}"
body = r.json()
assert body["answer"] == "echo: 你好"
assert "elapsed_ms" in body
print(f"  POST /chat   normal    -> {r.status_code} {body}")
ok("/chat 正常路径 200 + 返回 answer + elapsed_ms")

r = client.post("/chat", json={"user_input": "请帮我做一个很贵的任务"})
assert r.status_code == 402, f"BudgetExceeded 应 402, got {r.status_code}"
print(f"  POST /chat   budget    -> {r.status_code} {r.json()}")
ok("BudgetExceeded 正确映射 HTTP 402")

r = client.post("/chat", json={"user_input": "炸"})
assert r.status_code == 500
print(f"  POST /chat   error     -> {r.status_code} {r.json()}")
ok("内部异常正确映射 HTTP 500")

r = client.post("/chat", json={"user_input": ""})
assert r.status_code == 422, f"空 input 应被 Pydantic 挡掉 422, got {r.status_code}"
print(f"  POST /chat   empty     -> {r.status_code} (Pydantic 校验)")
ok("Pydantic min_length=1 正确挡掉空输入 (HTTP 422)")
