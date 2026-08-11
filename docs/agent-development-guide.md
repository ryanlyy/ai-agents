# AI Agent 开发指南:从 0 到 1 一步步构建

> 本指南假设你已经了解基础的 LLM API 调用,并对 [`mcp-server-basics.md`](./mcp-server-basics.md) 中的 MCP 协议有初步认识。我们会把 MCP 作为标准的「工具层」串进整个 Agent 架构。

---

## 0. 先理解 Agent 到底是什么

一个最小可用的 Agent 由四部分组成:

```
        ┌─────────────────────────────────────────────────┐
        │                    AGENT                        │
        │                                                 │
        │   ┌─────────┐     ┌─────────┐                   │
        │   │   LLM   │────▶│  Loop   │                   │
        │   │ (大脑)  │◀────│ (循环)  │                   │
        │   └─────────┘     └────┬────┘                   │
        │        ▲               │                        │
        │        │               ▼                        │
        │   ┌────┴────┐     ┌─────────┐                   │
        │   │ Memory  │     │  Tools  │                   │
        │   │ (记忆)  │     │  (手)   │                   │
        │   └─────────┘     └────┬────┘                   │
        └──────────────────────  │  ────────────────────  ┘
                                 ▼
                        外部 API / DB / 文件 / MCP Server
```

### 经典运行模式:ReAct(Reason + Act)

```
观察 (Observation) → 思考 (Thought) → 行动 (Action) → 调用工具 → 得到结果
        ↑                                                       │
        └───────────────────── 循环 ────────────────────────────┘
                  直到模型判断「任务完成」,输出 Final Answer
```

### 进阶模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **ReAct** | 边想边做,每一步都调用 LLM | 通用,任务步数较少 |
| **Plan-and-Execute** | 先规划全局,再分步执行 | 多步骤、有依赖的复杂任务 |
| **Reflexion** | 执行后自我反思,失败重试 | 对正确性要求高 |
| **Multi-Agent** | 多个 Agent 分工协作 | 角色明确的团队任务 |

---

## 1. Step 1:明确「做什么 Agent」

写代码之前,先回答 4 个问题,落到一个 `AGENT_SPEC.md`:

| 维度 | 示例 |
|------|------|
| **目标(Goal)** | "每天自动整理 GitHub PR 评论并发到 Slack" |
| **输入(Input)** | 自然语言指令 / 定时触发 / Webhook |
| **输出(Output)** | Markdown 报告 / Slack 消息 / DB 记录 |
| **约束(Constraints)** | 成本预算、延迟要求、合规、是否需要人工审批 |

> 没有清晰的目标,Agent 很容易做成"啥都能但啥都不好用"的玩具。

---

## 2. Step 2:选择技术栈

### 2.1 大模型

| 模型 | 优势 |
|------|------|
| **GPT-4.1 / GPT-5** (OpenAI) | 工具调用最稳,生态最全 |
| **Claude Opus 4.5 / Sonnet** (Anthropic) | 长上下文、推理强、原生 MCP |
| **Gemini 2.5** (Google) | 多模态、上下文巨大 |
| **Llama / Qwen / DeepSeek** | 本地部署、隐私敏感场景 |

关注三件事:**function calling / tool use 支持**、**上下文长度**、**单价**。

### 2.2 Agent 框架(挑一个就够)

| 框架 | 语言 | 适合场景 |
|------|------|----------|
| **LangGraph** | Python / TS | 复杂状态机、循环、多 Agent |
| **OpenAI Agents SDK** | Python / TS | 简单、官方、原生 handoff |
| **CrewAI** | Python | 多 Agent 角色协作 |
| **LlamaIndex Agents** | Python | 重 RAG、文档密集场景 |
| **Cursor TypeScript SDK** (`@cursor/sdk`) | TS | 复用 Cursor 编码 Agent 能力 |
| **从零手写** | 任意 | 学习用,生产慎选 |

### 2.3 工具层

**强烈建议直接用 MCP**,这样工具是可复用的,换框架不用重写。详见 [`mcp-server-basics.md`](./mcp-server-basics.md)。

---

## 3. Step 3:搭最小可运行原型(Hello-Agent)

不到 50 行,跑通 Agent 的"心跳":

```python
from openai import OpenAI
import json

client = OpenAI()

tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取某城市当前天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]

def get_weather(city: str) -> str:
    return f"{city} 今天 25°C 晴"

def run_agent(user_input: str, max_steps: int = 10) -> str:
    messages = [{"role": "user", "content": user_input}]
    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model="gpt-4.1", messages=messages, tools=tools
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = globals()[call.function.name](**args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })
    return "已达到最大步数限制"

print(run_agent("北京今天天气怎么样?"))
```

跑通这个,你就理解了 Agent 的核心机制:**LLM 决定下一步、工具执行、结果回填、循环**。

---

## 4. Step 4:把工具层抽成 MCP Server

第 3 步里的 `get_weather` 直接写在 Agent 里,耦合很重。把它搬到一个 **MCP Server**,好处:

- 任何 MCP 客户端(Cursor / Claude Desktop / 你的 Agent)都能复用。
- 工具的鉴权、日志、限流统一管理。
- Agent 代码只剩"大脑",业务工具完全解耦。

最小 MCP Server(Python,使用 `FastMCP`):

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather-server")

@mcp.tool()
def get_weather(city: str) -> str:
    """获取某城市当前天气"""
    return f"{city} 今天 25°C 晴"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

然后在你的 Agent 里通过 MCP Client SDK 连接它。详细模板参考 [`mcp-server-basics.md`](./mcp-server-basics.md) 第 6 节。

---

## 5. Step 5:加上 Memory(记忆)

Agent 没记忆 = 金鱼脑。记忆通常分三层:

| 层级 | 存储介质 | 用法 |
|------|----------|------|
| **短期(Short-term)** | 当前对话 `messages` 数组 | 直接拼进 prompt |
| **会话(Session)** | Redis / SQLite | 跨请求保存任务状态 |
| **长期(Long-term)** | 向量库(pgvector / Chroma / Qdrant / Milvus) | RAG 检索相关历史 |

### 简单实现:对话摘要 + 向量检索

```python
def remember(user_msg: str, agent_msg: str):
    summary = summarize(user_msg, agent_msg)
    embedding = embed(summary)
    vector_db.upsert(id=uuid(), embedding=embedding, metadata={"text": summary})

def recall(query: str, k: int = 5) -> list[str]:
    embedding = embed(query)
    return vector_db.query(embedding, top_k=k)
```

每轮开始前,先 `recall` 出相关历史,拼到 system prompt 里。

---

## 6. Step 6:加上 Planning(任务变复杂时)

简单任务 ReAct 就够;一旦任务多步骤、多依赖,引入显式规划:

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Planner  │───▶│ Executor │───▶│ Replanner│
│ 生成todo │     │ 逐步执行 │     │ 失败重规 │
└──────────┘     └──────────┘     └────┬─────┘
                       ▲                │
                       └────────────────┘
```

### LangGraph 示例骨架

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)
workflow.add_node("planner", plan_step)
workflow.add_node("executor", execute_step)
workflow.add_node("replanner", replan_step)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "executor")
workflow.add_conditional_edges(
    "executor",
    lambda s: "done" if s["finished"] else "replan",
    {"done": END, "replan": "replanner"},
)
workflow.add_edge("replanner", "executor")

app = workflow.compile()
```

---

## 7. Step 7:加上 Guardrails(防翻车)

| 风险 | 对策 |
|------|------|
| **死循环** | 设置 `max_iterations`(如 10 步) |
| **烧钱** | 限制 `max_tokens` + 成本预算告警 |
| **危险操作** | 删除、转账等走**人工审批**(Human-in-the-loop) |
| **提示词注入** | 把工具返回内容当**不可信输入**,做清洗/隔离 |
| **幻觉** | 要求引用来源 + 用 `json_schema` 强约束输出 |
| **越权调用** | 工具按用户角色加权限校验 |

> 一条铁律:**任何来自 LLM 或外部工具的输出,都视为不可信输入。**

---

## 8. Step 8:可观测性(Observability)

调试 Agent 最大的痛点是「看不见它在想什么」。必装其一:

| 工具 | 特点 |
|------|------|
| **LangSmith** | LangChain/LangGraph 原生,trace 最好看 |
| **Langfuse** | 开源、自托管友好 |
| **Helicone** | 接入简单,代理模式 |
| **Phoenix (Arize)** | 开源,evals 一体 |

最起码也要把每一步的 `Thought / Action / Observation / TokenUsage / Latency` 写成结构化日志(JSON Lines)。

> 没有 trace,后面所有优化都是盲调。

---

## 9. Step 9:评估(Evals)

凭感觉调 prompt = 在沼泽里走路。建立**测试集 + 评分器**:

1. **收集** 30~100 条真实任务样本,标注期望结果。
2. **评分**:
   - 规则评分(成功率、步数、成本、延迟)
   - **LLM-as-Judge**(用更强的模型当裁判)
3. **回归**:每改一次 prompt / 模型 / 工具,自动跑一遍。

常用工具:`promptfoo`、`DeepEval`、LangSmith Evaluations、`Braintrust`。

### 评分维度参考

| 维度 | 含义 |
|------|------|
| Task Success Rate | 任务是否真的完成 |
| Tool Call Accuracy | 调用了正确的工具 + 参数 |
| Step Efficiency | 是否用最少步数完成 |
| Cost / Latency | 单次任务成本与耗时 |
| Hallucination Rate | 是否编造事实 |

---

## 10. Step 10:部署 & 持续迭代

### 部署形态

| 形态 | 适用场景 |
|------|----------|
| **CLI 脚本** | 个人自动化 |
| **FastAPI / Next.js API** | Web 产品集成 |
| **Slack / Discord / 飞书 Bot** | 团队协作 |
| **定时任务**(cron / Temporal / Airflow) | 后台 Agent |
| **MCP Server + Cursor** | 把 Agent 嵌进编码工作流 |

### 上线后循环

```
埋点 → 看 trace → 发现问题 → 修 prompt / 加工具 / 换模型 → 跑 eval → 发布
  ↑                                                                    │
  └────────────────────────── 无限循环 ──────────────────────────────────┘
```

---

## 11. 学习路线图(2~3 周走完一遍)

| 时间 | 任务 |
|------|------|
| **Week 1** | 用 OpenAI Function Calling **手写**一个 ReAct Agent(Step 3),理解循环本质 |
| **Week 2** | 把工具改成 **MCP Server**,接入 **LangGraph**,加上 Memory |
| **Week 3** | 接 **Langfuse** 看 trace,写 10 条 eval,部署到一个**自己每天会用**的真实场景 |

> 关键原则:**先跑通,再优雅;先单 Agent,再多 Agent;先 ReAct,再 Plan-Execute。**

---

## 12. 常见坑 & 反模式

| 反模式 | 正确做法 |
|--------|----------|
| 一上来就上 Multi-Agent | 单 Agent 解决不了再说 |
| 给 Agent 装 50 个工具 | 工具描述吃 context,反而降准确率;按需启用 |
| 工具返回值不结构化 | 始终返回 JSON,字段命名清晰 |
| 提示词全堆 system | 拆分:system / few-shot / 工具描述 / 用户输入 |
| 没有失败回退 | 工具失败时,捕获异常并把错误信息回填给 LLM,让它自己重试 |
| 直接信任 LLM 输出 | 高风险动作必须 **Human-in-the-loop** |

---

## 13. 推荐资源

### 官方文档
- OpenAI Agents SDK: <https://github.com/openai/openai-agents-python>
- Anthropic Tool Use: <https://docs.anthropic.com/en/docs/agents-and-tools>
- LangGraph: <https://langchain-ai.github.io/langgraph/>
- MCP 规范: <https://spec.modelcontextprotocol.io>

### 经典论文
- **ReAct**: Yao et al. 2022 — *ReAct: Synergizing Reasoning and Acting in Language Models*
- **Reflexion**: Shinn et al. 2023 — *Reflexion: Language Agents with Verbal Reinforcement Learning*
- **Toolformer**: Schick et al. 2023
- **Voyager**: Wang et al. 2023(开放式 Agent 的代表作)

### 社区
- Awesome LLM Agents: <https://github.com/kyrolabs/awesome-langchain>
- Hugging Face Agents Course: <https://huggingface.co/learn/agents-course>

---

*Last updated: May 2026*
