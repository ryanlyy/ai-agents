"""
Step 6 — Plan-and-Execute Agent(LangGraph 状态机)。

与 agent.py 的 ReAct 不同,这里把任务拆成三个节点:

    ┌─────────┐    ┌──────────┐    ┌───────────┐
    │ Planner │───▶│ Executor │───▶│ Replanner │
    │ 列计划  │    │ 跑下一步 │    │ 决定继续? │
    └─────────┘    └──────────┘    └─────┬─────┘
                       ▲                  │
                       └──────────────────┘
                          (剩余步骤 > 0)
                                   │
                                   ▼
                                 [END]

每个 step 内部仍然是一个迷你 ReAct 循环(可调工具),保证简单步骤也能完成。

用法:
    python main_graph.py "你的复杂任务"

为聚焦演示,本文件不接 Memory / MCP / Trace。它直接复用 tools.py。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, StateGraph
from openai import OpenAI

from tools import TOOL_REGISTRY, TOOL_SCHEMAS


PLANNER_PROMPT = """你是一个规划师。请把用户任务拆成 2-5 个**线性、可执行**的子步骤。

要求:
- 每个步骤必须能用一次或几次工具调用搞定。
- 不要用编号,直接按行返回纯文本步骤,一行一个。
- 不要在最后加总结,Replanner 会处理。
- 用中文。

用户任务:{task}

仅返回步骤列表(每行一个),不要其他内容:"""

EXECUTOR_SYSTEM = """你是一个执行助手,正在完成更大任务里的某一个子步骤。
你可以使用工具,但只为完成**当前**子步骤,不要去做后面的步骤。
得到结果后,用 1-2 句话陈述结论。"""

REPLANNER_PROMPT = """你是规划师。原始任务和已完成的步骤如下:

【原始任务】
{task}

【已完成的步骤与结论】
{past_steps}

【剩余计划】
{remaining_plan}

请二选一回答:
1. 如果根据已知信息已能给出**最终答案**,以 `FINAL: <答案>` 开头一次性输出最终答案。
2. 否则给出**更新后的剩余步骤列表**,一行一个,不要编号、不要其他内容。

回答:"""


class GraphState(TypedDict, total=False):
    task: str
    plan: list[str]
    past_steps: list[tuple[str, str]]
    final_answer: str | None
    step_count: int


@dataclass
class GraphConfig:
    model: str
    max_steps: int = 8


# ANSI 颜色(与 agent.py 同款,但本文件独立可用)
class C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    RED = "\033[31m"
    BOLD = "\033[1m"


class PlanExecuteAgent:
    """LangGraph 实现的 Plan-and-Execute Agent。"""

    def __init__(self, config: GraphConfig | None = None):
        self.client = OpenAI()
        self.config = config or GraphConfig(
            model=os.getenv("AGENT_MODEL", "gpt-4.1-mini"),
            max_steps=int(os.getenv("AGENT_MAX_STEPS", "8")),
        )
        self.app = self._build_graph()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def run(self, task: str) -> str:
        print(f"\n{C.BOLD}{C.CYAN}USER ▶{C.RESET}{C.DIM} [GRAPH]{C.RESET} {task}")
        t0 = time.perf_counter()
        state: GraphState = {"task": task, "plan": [], "past_steps": [], "step_count": 0}
        result = self.app.invoke(state, {"recursion_limit": self.config.max_steps * 4})
        elapsed = time.perf_counter() - t0
        answer = result.get("final_answer", "(没有得到 final_answer)")
        print(f"\n{C.BOLD}{C.GREEN}AGENT ▶{C.RESET} {answer}")
        print(f"{C.DIM}══ Total ══ elapsed={elapsed:.2f}s steps={result.get('step_count', 0)}{C.RESET}\n")
        return answer

    # ------------------------------------------------------------------
    # 节点
    # ------------------------------------------------------------------

    def _planner(self, state: GraphState) -> dict:
        prompt = PLANNER_PROMPT.format(task=state["task"])
        resp = self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        plan = [ln.strip(" -•*") for ln in text.splitlines() if ln.strip()]
        plan = [p for p in plan if p][:5]

        print(f"\n{C.BOLD}{C.BLUE}── Planner ──{C.RESET}")
        for i, p in enumerate(plan, 1):
            print(f"  {i}. {p}")
        return {"plan": plan}

    def _executor(self, state: GraphState) -> dict:
        if not state["plan"]:
            return {}
        current = state["plan"][0]
        step_no = state.get("step_count", 0) + 1
        print(f"\n{C.BOLD}{C.MAGENTA}── Executor (Step {step_no}) ──{C.RESET} {current}")

        result_text = self._mini_react(current)

        past_steps = list(state.get("past_steps", []))
        past_steps.append((current, result_text))
        return {
            "past_steps": past_steps,
            "plan": state["plan"][1:],
            "step_count": step_no,
        }

    def _replanner(self, state: GraphState) -> dict:
        past_block = (
            "\n".join(f"- {s} → {r}" for s, r in state.get("past_steps", []))
            or "(暂无)"
        )
        remaining = "\n".join(f"- {s}" for s in state.get("plan", [])) or "(暂无)"
        prompt = REPLANNER_PROMPT.format(
            task=state["task"], past_steps=past_block, remaining_plan=remaining
        )
        resp = self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()

        if text.upper().startswith("FINAL:"):
            answer = text[len("FINAL:") :].strip()
            print(f"\n{C.BOLD}{C.YELLOW}── Replanner ──{C.RESET} 已得出 final answer")
            return {"final_answer": answer}

        new_plan = [ln.strip(" -•*") for ln in text.splitlines() if ln.strip()][:5]
        print(f"\n{C.BOLD}{C.YELLOW}── Replanner ──{C.RESET} 剩余计划更新为 {len(new_plan)} 步")
        for i, p in enumerate(new_plan, 1):
            print(f"  {i}. {p}")
        return {"plan": new_plan}

    # ------------------------------------------------------------------
    # 子循环:用一次 ReAct 完成单个 step
    # ------------------------------------------------------------------

    def _mini_react(self, sub_task: str, max_iters: int = 4) -> str:
        messages = [
            {"role": "system", "content": EXECUTOR_SYSTEM},
            {"role": "user", "content": sub_task},
        ]
        for _ in range(max_iters):
            resp = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return (msg.content or "").strip()
            for call in msg.tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                func = TOOL_REGISTRY.get(name)
                try:
                    result = func(**args) if func else f"未知工具 {name}"
                except Exception as exc:
                    result = f"错误:{exc}"
                snippet = result if len(result) <= 150 else result[:150] + "…"
                print(f"  {C.DIM}↳ {name}({json.dumps(args, ensure_ascii=False)}) → {snippet}{C.RESET}")
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )
        return "(子任务超过迷你 ReAct 上限,未完成)"

    # ------------------------------------------------------------------
    # 构图
    # ------------------------------------------------------------------

    def _should_continue(self, state: GraphState) -> str:
        if state.get("final_answer"):
            return "end"
        if not state.get("plan"):
            # 没有 final_answer 也没剩余计划 —— 让 replanner 兜底再判一次
            return "replanner"
        if state.get("step_count", 0) >= self.config.max_steps:
            return "end"
        return "executor"

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("planner", self._planner)
        graph.add_node("executor", self._executor)
        graph.add_node("replanner", self._replanner)

        graph.set_entry_point("planner")
        graph.add_edge("planner", "executor")
        graph.add_edge("executor", "replanner")
        graph.add_conditional_edges(
            "replanner",
            self._should_continue,
            {"executor": "executor", "replanner": "replanner", "end": END},
        )
        return graph.compile()
