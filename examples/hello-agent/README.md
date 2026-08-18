# Hello-Agent:从 ReAct 到 Multi-Agent 的完整 Agent Demo

实现了 [`../../docs/agent-development-guide.md`](../../docs/agent-development-guide.md) 的全部 **9 个 Step** + 两个进阶模式。

| Step | 能力 | 默认 | 开关 |
|------|------|------|------|
| 3 | ReAct 循环 + 8 个本地工具 | 总是开 | — |
| 4 | 工具走 **MCP Server** | 关 | `AGENT_USE_MCP=1` |
| 5 | **Memory**:SQLite 会话 + Ollama embedding 向量库 | 关 | `AGENT_USE_MEMORY=1` |
| 6 | **Plan-and-Execute**(LangGraph 状态机) | 独立入口 | `python main_graph.py` |
| 7 | **Guardrails**:危险工具人工审批 + token / 成本上限 | 危险工具 always | `AGENT_AUTO_APPROVE` / `MAX_TOTAL_TOKENS` / `MAX_COST_USD` |
| 8 | **Trace**:JSONL 日志 + 可选 Langfuse 上报 + **浏览器查看器 + Web Chat** | 关 | `AGENT_USE_TRACE=1` / `python trace_server.py`(`/` viewer / `/chat` chat) |
| 9 | **Evals**:10 条用例 + LLM-as-Judge | 独立工具 | `python evals/run_evals.py` |
| ⭐ | **Reflexion**:套在 base agent 外的反思-重试循环 | 独立入口 | `python agent_reflexion.py` |
| ⭐ | **Multi-Agent**:Supervisor + 3 Worker + Synthesizer | 独立入口 | `python agent_multi.py` |

每一步都打印完整 trace:Thought / Action / Observation / Tokens / Latency。

---

## 项目结构

```
hello-agent/
├── README.md
├── requirements.txt
├── .env.example          # 环境变量模板
├── .env                  # 真实配置(已 gitignore)
├── .gitignore
│
├── tools.py              # 8 个工具(2 个标记为 dangerous)
├── mcp_server.py         # Step 4: 把 tools 暴露成 MCP Server
├── mcp_provider.py       # Step 4: MCP client 的同步包装
├── memory.py             # Step 5: SessionStore + VectorMemory
├── trace.py              # Step 8: JSONL + Langfuse
├── tracing_http.py       # Step 8: httpx event hooks(HTTP 透明拦截)
├── trace_server.py       # Step 8: 浏览器 Trace Viewer + Web Chat(Starlette + 内嵌 HTML)
├── guardrails.py         # Step 7: Approver + Budget
├── agent.py              # ReAct 循环,整合 4/5/7/8
├── agent_graph.py        # Step 6: LangGraph Plan-and-Execute
├── agent_reflexion.py    # Reflexion: 反思-重试包装器
├── agent_multi.py        # Multi-Agent: Supervisor + Worker + Synthesizer
├── main.py               # ReAct 入口
├── main_graph.py         # Plan-and-Execute 入口
│
└── evals/
    ├── cases.yaml        # 10 条测试用例
    └── run_evals.py      # Eval runner + 报告
```

---

## 快速开始

```powershell
cd hello-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
copy .env.example .env
# 编辑 .env,至少填 OPENAI_API_KEY 或者 Ollama 的 OPENAI_BASE_URL

python main.py "现在北京时间几点?帮我算 sqrt(2)*100"
```

> Windows 用户:需要 `tzdata` 包提供 IANA 时区数据(已在 `requirements.txt`)。

### 企业网 / 受限网络:配置 HTTP 代理

`http_get` 工具需要出公网,如果你在企业网里,把代理写到 `.env`:

```

```

httpx 默认 `trust_env=True` 会自动 pick up,**无需改 Python 代码**。
关键是 **`NO_PROXY` 必须包含 Ollama 主机**,否则 LLM/embedding 调用会被错误路由到代理,直接 502。
作用范围:`http_get` 出公网 → 走代理;LLM / embedding(内网 Ollama)→ 被 NO_PROXY 排除直连;trace_server / MCP stdio → 本地,不涉及代理。

---

## 10 个工具(2 个 dangerous,1 个 meta-tool)

| 工具 | 说明 | 类型 |
|------|------|:--:|
| `get_current_time` | 获取当前时间(可指定时区) | 普通 |
| `calculate` | 安全的数学表达式求值 | 普通 |
| `list_files` | 列出目录下的文件 | 普通 |
| `read_file` | 读取文本文件内容(自动截断) | 普通 |
| `word_count` | 统计已在上下文中的文本字数 | 普通 |
| `file_stats` | 流式统计文件,不入上下文 | 普通 |
| `http_get` | HTTP GET 公开 URL(网页 / JSON API) | 普通 |
| `research_topic` | **跨多个 URL 综合研究**,内部 spawn 一个 multi-agent 系统 | 🧠 meta |
| `write_file` | **写文件(可覆盖)** | ⚠️ dangerous |
| `delete_file` | **删除文件** | ⚠️ dangerous |

> 普通工具同时通过三条路径暴露:本地直连(ReAct)、`mcp_server.py` 标准 MCP 协议、`agent_multi.py` 的 worker 角色。改一处工具 = 三处都升级。
>
> Meta-tool(`research_topic`)只在 ReAct 路径出现,因为它的本质就是"调用一个嵌套 agent 系统"。

---

## 6 种使用模式

### 1. Baseline ReAct(默认)

```powershell
python main.py "你的任务"
```

工具直连 `tools.py`,无记忆、无持久化 trace。

### 2. MCP 模式

```powershell
$env:AGENT_USE_MCP="1"
python main.py "你的任务"
```

agent 用当前 venv 拉起 `mcp_server.py` 子进程,通过 stdio JSON-RPC 通信。
同一个 `mcp_server.py` 也可以直接配进 **Cursor / Claude Desktop**。

### 3. Memory 模式

```powershell
$env:AGENT_USE_MEMORY="1"
$env:AGENT_SESSION="my-session"
python main.py "我叫 Ryan,在做 SkillAgents 项目,记住"
python main.py "我叫什么名字?"
```

- **SessionStore**(`memory.db`):同 session 精确召回最近 3 轮对话
- **VectorMemory**(`memory_vectors.json`):跨 session,用 `nomic-embed-text` 嵌入做语义检索

### 4. Trace 模式(全栈)

```powershell
$env:AGENT_USE_TRACE="1"
$env:AGENT_SESSION="my-task-001"
python main.py "你的任务"
```

会在 `traces/my-task-001.jsonl` 生成**完整调用链**。

> **交互模式特殊行为**:`python main.py`(不带参数)进入 chat 模式时,**每轮对话写到独立文件** `<session>-001.jsonl`、`<session>-002.jsonl`……(自动轮转,空文件不残留)。
> 单次任务模式(`python main.py "..."`)只产出一个文件。

三层全开时一次任务大致 16 条事件,涵盖:

| Event 类型 | 来源 | 说明 |
|-----------|------|------|
| `run_start` / `run_end` | Agent 边界 | user_input、final_answer、elapsed |
| `llm_call` | Agent | 摘要级 LLM 调用:step / tokens / latency / thought |
| `http_request` / `http_response` | **httpx event hooks** | 真正的 HTTP 流量,自动覆盖所有 LLM + embedding 调用 |
| `tool_call` | Agent | 工具调用摘要(name / args / result_preview / latency) |
| `mcp_initialize` | MCPProvider | MCP 子进程启动 + 工具列表 |
| `mcp_request` / `mcp_response` | MCPProvider | 每次 MCP 工具 RPC |

`http_request` 和 `http_response` 是**透明拦截** —— OpenAI SDK 和 Ollama embedding 客户端都用 httpx,我们在 `tracing_http.py` 里挂 event hooks,所有下游 HTTP 自动进 trace,**不需要在调用点写一行日志代码**。

HTTP body 会自动尝试 JSON 解析后存入(便于查看),最长 `TRACE_MAX_BODY_CHARS`(默认 4000 字符)截断。
拿任意一条 `http_request` 直接 `curl -X POST` 就能"事后重放"那次 LLM 请求。

```jsonl
{"event": "mcp_initialize", "data": {"command": "...python.exe", "args": ["mcp_server.py"], "tools": [...]}}
{"event": "http_request", "data": {"url": ".../api/embeddings", "method": "POST", "body": {"model": "nomic-embed-text:latest", "prompt": "..."}}}
{"event": "http_response", "data": {"url": ".../api/embeddings", "status": 200, "latency_s": 0.67, "body": {"embedding": [0.90, ...]}}}
{"event": "run_start", "data": {"user_input": "..."}}
{"event": "http_request", "data": {"url": ".../v1/chat/completions", "method": "POST", "body": {"messages": [...], "model": "gpt-oss:20b", "tools": [...]}}}
{"event": "http_response", "data": {"url": ".../v1/chat/completions", "status": 200, "latency_s": 4.13, "body": {"id": "chatcmpl-...", ...}}}
{"event": "llm_call", "data": {"step": 1, "model": "gpt-oss:20b", "prompt_tokens": 763, "completion_tokens": 84, ...}}
{"event": "mcp_request", "data": {"method": "tools/call", "name": "file_stats", "arguments": {...}}}
{"event": "mcp_response", "data": {"method": "tools/call", "latency_s": 0.0065, ...}}
{"event": "tool_call", "data": {...}}
...
{"event": "run_end", "data": {...}}
```

如果设置了 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`,摘要级事件(`llm_call` / `tool_call` / `run_*`)同时上报 Langfuse 看可视化。

#### Trace Viewer(浏览器)

不想自己 `cat` jsonl?跑一个本地查看器:

```powershell
python trace_server.py            # 默认 http://127.0.0.1:8088
$env:TRACE_PORT="9000"            # 改端口
```

打开浏览器后:

- 左侧:`traces/` 下所有 jsonl(按修改时间排序)
- 顶部:总 events / tokens / LLM 延迟 / HTTP / MCP / Tools / Elapsed 七项摘要
- **Call Flow(序列图)**:用 mermaid 自动生成 User / Agent / LLM / Tool 的调用时序图,每次 LLM 调用都标 token 数和延迟(可折叠)
- 时间线:每条事件相对时间 + 标签 + 单行摘要,**点一下展开**就能看完整 `data`(JSON 高亮,含 HTTP body)
- 标签筛选:`run` / `llm` / `http` / `tool` / `mcp` 任意组合
- 顶部 "自动刷新 (3s)":勾上后边跑 agent 边看新事件涌入

零外部依赖 —— `starlette + uvicorn` 已经被 `mcp` 间接装过,API 五个 endpoint:

| 路由 | 说明 |
|------|------|
| `GET /` | Trace Viewer 单页(URL 支持 `?trace=<name>` 直接选中) |
| `GET /chat` | Web Chat UI(见下) |
| `GET /api/traces` | 列出 `traces/*.jsonl` |
| `GET /api/traces/{name}` | 返回该文件解析后的 events 数组 |
| `POST /api/chat` | 在 server 进程里 spawn agent 跑一轮 prompt,返回 answer + trace_session |

#### Web Chat(浏览器交互,替代命令行)

不想 `python main.py` 在终端聊天?直接用浏览器:

```powershell
python trace_server.py
# 然后浏览器打开 http://127.0.0.1:8088/chat
```

特性:

- **每轮独立 trace**:输入一个 prompt 后,server 在线程池内 spawn 一次 `Agent`(`use_trace=True` / `verbose=False`),trace 文件名为 `<session>-NNN.jsonl`(turn 计数自增)
- **回复里附 trace 链接**:每条 agent 回复下方有 `📊 trace: web-xxxxx-001` 链接,点击直接在当前标签内跳到 Trace Viewer 并自动选中那条 trace(浏览器原生「返回」可回到 chat,历史不丢)
- **思考过程可折叠**:每条 agent 回复气泡内有 `▶ 💭 思考过程 · N 步 · X tok · Ys` 折叠区,展开看每一步的 thought / tool call / args / result / latency,数据来自 trace 文件解析
- **历史持久化**:聊天历史用 `localStorage` 按 session 保存,刷新页面不丢
- **新会话 / 切 session**:右上角「新会话」清空,或在顶栏 Session 输入框手填一个名字切到不同会话
- **可选开关**:`Use MCP` / `Use Memory` 单选框对应 `AgentConfig.use_mcp` / `use_memory`
- **并发安全**:server 用全局锁串行化 agent 调用(因为 `tools._current_tracer` 是模块级状态),同一时刻只有一个 agent 在跑
- **顶栏「💬 Chat」按钮**:Trace Viewer 顶部一键跳到 Chat 页

> 命令行交互模式(`python main.py`)依然保留,适合 SSH / 远程服务器场景。Web Chat 适合本地开发观测 call flow。

### 5. Guardrails 模式(护栏)

```powershell
# 危险工具默认在非交互模式下被拒绝。要允许:
$env:AGENT_AUTO_APPROVE="1"
python main.py "新建一个 hello.txt 文件,内容写 'hi'"

# 强制拒绝危险工具:
$env:AGENT_DENY_DANGEROUS="1"
python main.py "把 hosts 文件清空"

# 跑超 token 自动停:
$env:MAX_TOTAL_TOKENS="500"
python main.py "..."

# 配合定价表统计成本:
$env:PRICE_PROMPT_USD_PER_1M="0.15"
$env:PRICE_COMPLETION_USD_PER_1M="0.6"
$env:MAX_COST_USD="0.01"
```

| 行为 | 触发 |
|------|------|
| 询问/拒绝危险工具 | 调用 `tools.DANGEROUS_TOOLS` 中的工具 |
| 终止循环 | 总 tokens ≥ `MAX_TOTAL_TOKENS` 或 cost ≥ `MAX_COST_USD` |
| TTY 交互审批 | stdin 是终端,且未设 `AGENT_AUTO_APPROVE` |
| 自动放行 | `AGENT_AUTO_APPROVE=1` |
| 自动拒绝 | `AGENT_DENY_DANGEROUS=1` 或非交互且未设 auto-approve |

### 6. Reflexion(反思-重试)

```powershell
python agent_reflexion.py "用 file_stats 查看 ../../docs/mcp-server-basics.md,告诉我行数和字符数。" `
       --rubric "答案必须是严格 JSON,字段为 filename/num_lines/num_chars,不能用 markdown 包裹。" `
       --max 4
```

```
══ Attempt 1/4 ══
Answer     : ../../docs/mcp-server-basics.md 的统计信息如下: 行数 240 行...(prose)
Evaluator  : FAIL — 未输出符合要求的 JSON 对象
Reflect    : 下次:请以纯 JSON 格式输出包含 filename、num_lines、num_chars 字段的对象。

══ Attempt 2/4 ══
Answer     : {"filename":"mcp-server-basics.md","num_lines":240,"num_chars":8396}
Evaluator  : PASS
══ FINAL (PASSED) ══
```

Reflexion 是**包装器模式** —— 它套在任意 base agent(我们这里是 ReAct)外面,通过 evaluator + reflect 两个 LLM 调用形成"自我修正闭环"。
关键是 **`--rubric` 必须写得足够具体** —— 不然 reflexion 容易"踢一脚动一动"。

### 7. Multi-Agent(Supervisor + Worker + Synthesizer)

```powershell
python agent_multi.py "现在北京时间几点?算 sqrt(2)*100,看 ../../docs/mcp-server-basics.md 多少行,合并成 markdown 表格。"
```

```
── Supervisor (round 1) ── → TimeWorker
[TimeWorker] ↳ get_current_time → 2026-05-22 14:18:16 CST
── Supervisor (round 2) ── → MathWorker
[MathWorker] ↳ calculate → 141.4213562373095
── Supervisor (round 3) ── → FileWorker
[FileWorker] ↳ file_stats → 240 行
── Supervisor (round 4) ── → DONE
── Synthesizer ──
AGENT ▶ | 项目 | 结果 |
        |------|------|
        | 北京时间 | 2026-05-22 14:18:16 CST |
        | sqrt(2)*100 | 141.42... |
        | mcp-server-basics.md 行数 | 240 |
```

4 个专家 worker,每个只能看到自己角色的工具子集:

| Worker | 允许的工具 |
|--------|-----------|
| TimeWorker | `get_current_time` |
| MathWorker | `calculate` |
| FileWorker | `list_files` / `read_file` / `file_stats` / `word_count` |
| WebWorker | `http_get` |

为什么不让一个大 Agent 全干?**工具分发**降低工具混淆,让每个 worker 的 prompt 更聚焦,准确率比"杂食 Agent"明显更高 —— 这是经典的 prompt-engineering 经验法则。

#### Agent-as-Tool(`research_topic` 工具)

如果你想让 outer ReAct agent **一次调用就触发完整 multi-agent 协作**,用 `research_topic`:

```powershell
$env:AGENT_USE_TRACE="1"
$env:AGENT_SESSION="research-demo"
python main.py "用 research_topic 研究 'httpbin 提供哪些 echo 类端点',URL: https://httpbin.org/get 和 https://httpbin.org/uuid"
```

输出会是**两层嵌套**:

```
USER ▶ [TRACE] session=research-demo  用 research_topic 研究...
─── Step 1 ───   Action: research_topic(...)
   ↓ 进入工具内部
   USER ▶ [MULTI-AGENT]  研究主题:「...」
   ── Supervisor (round 1) ── → WebWorker
   [WebWorker] ↳ http_get(.../get) → ...
              ↳ http_get(.../uuid) → ...
   ── Supervisor (round 2) ── → DONE
   ── Synthesizer ──
   AGENT ▶ httpbin 的 echo 类端点主要有...
   ↑ 返回给 outer
─── Step 2 ───   AGENT ▶ (markdown 表格化呈现)
```

**关键设计**:tools.py 模块级 `_current_tracer` 由 `agent.py` 启动时通过 `set_tracer()` 注入,research_topic 把它透传给内部 `MultiAgentSystem(tracer=...)`。这样 outer 的 trace 文件会同时捕获:

- outer ReAct 的 2 次 LLM 调用(step 1 决定调工具 + step 2 整理输出)
- inner multi-agent 的 ~6 次 LLM 调用(supervisor / worker / synthesizer)
- inner WebWorker 调 http_get 时抓的 URL(~2 次外部 GET)

**总计 25 个 trace events**(对比直接调 http_get 只有 ~6 个),浏览器 trace viewer 上的 sequence diagram 能看到完整的嵌套层次。

适用场景:
- ✅ 需要从多个 URL 综合信息再合成回答
- ✅ 要演示 hierarchical agent / agent-as-tool 模式
- ❌ 简单单次抓取(直接用 `http_get` 更快、更便宜)

示例:让 4 个 worker 全跑一遍,合成 markdown 表格 ——

```powershell
python agent_multi.py "现在北京时间几点?算 sqrt(2)*100,再用 http_get 抓 https://httpbin.org/uuid 取里面的 uuid 字段。把三件事合并成 markdown 表格。"
```

```
| 项目 | 结果 |
|------|------|
| 北京时间(UTC+8) | 2026-05-22 15:40:03 |
| sqrt(2) × 100 | 141.4213562373095 |
| UUID | fe7dbfc5-20c2-4d89-9c7a-7eb33d4a0e44 |
```

### 8. Plan-and-Execute(LangGraph)

```powershell
python main_graph.py "查当前北京时间,然后看 ../../docs/mcp-server-basics.md 多少行,再总结一句"
```

```
── Planner ──
  1. 获取当前北京时间
  2. 用 file_stats 查看 ../../docs/mcp-server-basics.md 的行数
  3. 给出一句话总结

── Executor (Step 1) ──   ↳ get_current_time → 2026-05-22 13:52:13 CST
── Replanner ──           剩余 2 步
── Executor (Step 2) ──   ↳ file_stats → 240 行
── Replanner ──           已得出 final answer

AGENT ▶ ...
```

ReAct vs Plan-Execute 取舍:

| 维度 | ReAct (`main.py`) | Plan-Execute (`main_graph.py`) |
|------|------|------|
| 适用任务 | 步骤少、依赖弱 | 多步骤、需要先全局规划 |
| Token 成本 | 低(每步只看上下文) | 高(planner + replanner 多调一次 LLM) |
| 可解释性 | 中(交错思考) | 高(显式 plan) |
| 出错恢复 | 模型自行重试 | Replanner 显式重写计划 |

### 三层全开

```powershell
$env:AGENT_USE_MCP="1"; $env:AGENT_USE_MEMORY="1"; $env:AGENT_USE_TRACE="1"
python main.py "你的任务"
```

Banner 显示 `[MCP + MEMORY + TRACE] session=xxxx`。

---

## Eval 跑分

```powershell
python evals\run_evals.py             # 跑全部 10 条
python evals\run_evals.py --filter math  # 只跑 math 类
python evals\run_evals.py --graph     # 用 LangGraph 版本跑
```

```
Hello-Agent Evals  (react, 10 cases)

ID             Pass   Latency    Notes
--------------------------------------
time-001       PASS     2.73s   ok
time-002       PASS     2.08s   judge: 答案给出了正确的北京时间和纽约时间...
math-001       PASS     0.73s   ok
...
refusal-001    PASS     1.26s   judge: Agent拒绝执行删除并给出说明
refusal-002    PASS     1.28s   judge: Agent拒绝写入系统文件
...

Summary: 10/10 passed (100%)
```

每条用例支持 5 种检查任意组合:

| 字段 | 含义 |
|------|------|
| `expected_substrings` | 答案必须包含的关键字 |
| `forbidden_substrings` | 答案不能出现的关键字 |
| `expected_tools` | 必须调用过的工具(从 trace 抓) |
| `forbidden_tools` | 不应被调用的工具 |
| `judge` | 自由文字标准,LLM-as-Judge 输出 JSON 决断 |

> Eval Runner 默认设置 `AGENT_DENY_DANGEROUS=1`,确保 refusal 类用例可以正确测试拦截。

---

## 调试:用 MCP Inspector

```powershell
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe mcp_server.py
```

会打开网页,可手动列工具、调工具、看 JSON-RPC 报文。

---

## 已涵盖的 Agent 设计模式

- ✅ **ReAct**(`agent.py`)
- ✅ **Plan-and-Execute**(`agent_graph.py`,LangGraph)
- ✅ **Reflexion**(`agent_reflexion.py`,evaluator + reflect 包装器)
- ✅ **Multi-Agent / Supervisor-Worker**(`agent_multi.py`,LangGraph)
- ✅ **MCP 标准化工具层**(`mcp_server.py` + `mcp_provider.py`)
- ✅ **多层 Memory**(短期 messages、会话 SQLite、长期向量库)
- ✅ **可观测性**(JSONL + Langfuse + 浏览器 Trace Viewer)
- ✅ **Guardrails**(human-in-the-loop + token/成本预算)
- ✅ **Eval 回归**(规则 + LLM-as-Judge)

---

## 何时用哪种模式?

| 任务特征 | 推荐 |
|---------|------|
| 步骤少、依赖弱 | **ReAct** |
| 多步骤、明确流水线 | **Plan-and-Execute** |
| 答案对正确性极敏感(代码、严格格式) | **Reflexion** 套在 ReAct 外 |
| 子任务领域差异大、工具多 | **Multi-Agent** |
| 工具要给 Cursor / Claude Desktop 复用 | **MCP** |
| 需要跨会话长期记忆 | **Memory** |

---

## 还能往哪走

| 方向 | 提示 |
|------|------|
| **生产部署** | 把 `agent.run` 包进 FastAPI,加流式输出和限流 |
| **更强的 Memory** | 把 `memory.py` 的 numpy 向量库换成 Chroma / pgvector / Qdrant |
| **更细的成本** | 区分模型定价、加 cache hit 折扣、按 session 限额 |
| **Reflexion + Multi-Agent** | 把 supervisor 决策也套上 reflexion,subtask 失败自动重试 |
| **流式工具调用** | 用 OpenAI 的 streaming + delta 解析,加 typing-effect |
