"""
Multi-Agent:经典的 Supervisor / Worker / Synthesizer 模式(LangGraph 实现)。

    ┌──────────────┐
    │  Supervisor  │  决策:把当前子任务分派给哪个 worker?或宣告 DONE?
    └─┬───┬───┬───┬─┘
      │   │   │   │
      ▼   ▼   ▼   ▼
    [Time][Math][File][Web]   4 个专家 worker(每个只持有自己领域的工具子集)
      │   │   │   │
      └───┴───┴───┴── 输出汇集 → state.worker_outputs ──┐
                                                       ▼
                                              ┌──────────────┐
                                              │ Synthesizer  │ 合成最终答案
                                              └──────────────┘

要点:
  - 每个 Worker 是一个**独立小 ReAct 循环**,系统 prompt 写明"你是 X 专家"。
  - Tool 子集由角色限定,降低工具混淆,提高准确率(经典 prompt-engineering 技巧)。
  - Supervisor 用 JSON mode 输出结构化决策,确保路由可解析。
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from openai import OpenAI

from tools import TOOL_REGISTRY, TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# 颜色
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Worker:小型 ReAct,工具子集
# ---------------------------------------------------------------------------


@dataclass
class Worker:
    name: str
    description: str  # 给 Supervisor 看,决定何时分派给我
    system_prompt: str
    allowed_tools: set[str]
    color: str = C.MAGENTA

    def schemas(self) -> list[dict]:
        return [
            s for s in TOOL_SCHEMAS if s["function"]["name"] in self.allowed_tools
        ]

    def run(self, sub_task: str, client: OpenAI, model: str, max_iters: int = 4, tracer=None) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": sub_task},
        ]
        print(f"\n{self.color}[{self.name}]{C.RESET} {C.DIM}▶ subtask:{C.RESET} {sub_task}")

        if tracer is not None:
            tracer.push_actor(f"worker-{self.name}")

        try:
            return self._run_loop(messages, client, model, max_iters)
        finally:
            if tracer is not None:
                tracer.pop_actor()

    def _run_loop(self, messages, client, model, max_iters):
        for _ in range(max_iters):
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=self.schemas() or None,
                tool_choice="auto" if self.schemas() else None,
            )
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                final = (msg.content or "").strip()
                print(f"{self.color}[{self.name}]{C.RESET} {C.DIM}done:{C.RESET} {self._snippet(final)}")
                return final

            for call in msg.tool_calls:
                name = call.function.name
                if name not in self.allowed_tools:
                    result = f"错误:{self.name} 不允许调用工具 '{name}'。"
                else:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        func = TOOL_REGISTRY.get(name)
                        result = func(**args) if func else f"未知工具 {name}"
                    except Exception as exc:
                        result = f"错误:{exc}"
                snippet = result if len(result) <= 150 else result[:150] + "…"
                print(f"  {self.color}↳ {name}({call.function.arguments}){C.RESET} {C.DIM}→ {snippet}{C.RESET}")
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )

        return "(超出 worker 最大迭代步数,未完成)"

    @staticmethod
    def _snippet(text: str, n: int = 200) -> str:
        text = text.replace("\n", " ").strip()
        return text if len(text) <= n else text[:n] + "…"


# ---------------------------------------------------------------------------
# 角色定义
# ---------------------------------------------------------------------------


WORKERS: dict[str, Worker] = {
    "TimeWorker": Worker(
        name="TimeWorker",
        description="时间专家:获取/换算各时区当前时间。",
        system_prompt=(
            "你是时间助手,只回答与日期/时间/时区相关的问题。"
            "需要时使用 get_current_time。完成后用一句话陈述结论,不要做范围外的事。"
        ),
        allowed_tools={"get_current_time"},
        color=C.CYAN,
    ),
    "MathWorker": Worker(
        name="MathWorker",
        description="计算专家:做数学表达式求值。",
        system_prompt=(
            "你是计算助手,只解决数学计算问题。"
            "用 calculate 完成求值。给出结果时直接报数字,不要冗长解释。"
        ),
        allowed_tools={"calculate"},
        color=C.YELLOW,
    ),
    "FileWorker": Worker(
        name="FileWorker",
        description="文件专家:列目录、读文件、统计行/字符。",
        system_prompt=(
            "你是文件助手,处理本地文件相关任务。"
            "可用工具:list_files / read_file / file_stats / word_count。"
            "需要统计行数/字符数,优先使用 file_stats(不耗 context)。"
        ),
        allowed_tools={"list_files", "read_file", "file_stats", "word_count"},
        color=C.MAGENTA,
    ),
    "WebWorker": Worker(
        name="WebWorker",
        description="网络专家:抓取公开 URL 的内容(网页 / JSON API),回答涉及外部数据的问题。",
        system_prompt=(
            "你是网络助手,通过 http_get 抓取公开 URL 后回答问题。"
            "工作要点:"
            "1. 拿到响应后只引用关键片段,不要把整个页面塞进答案。"
            "2. JSON API 直接解析提取需要的字段。"
            "3. 4xx/5xx 状态码视为失败,可换协议(http→https)或换 URL 重试一次。"
            "4. 不要尝试访问内网/本机地址,只抓真正的公开互联网资源。"
        ),
        allowed_tools={"http_get"},
        color=C.GREEN,
    ),
}


# ---------------------------------------------------------------------------
# State & Graph
# ---------------------------------------------------------------------------


class MultiState(TypedDict, total=False):
    task: str
    worker_outputs: list[dict]  # [{worker, subtask, output}]
    next_worker: str  # "TimeWorker" / "MathWorker" / "FileWorker" / "DONE"
    current_subtask: str
    final_answer: str
    rounds: int


SUPERVISOR_PROMPT = """你是 supervisor,管理一个由专家 worker 组成的小团队。

【可用 worker】
{roster}

【用户原始任务】
{task}

【已经完成的工作】
{past}

请判断接下来要做什么,**只输出 JSON**,字段如下:
- next_worker:从 {names} 中选一个,或者 "DONE" 表示工作做完可以汇总。
- subtask:如果不是 DONE,给该 worker 一个**简洁、单一目标**的子任务描述(中文)。

注意:
- 一次只派一个 worker,不要在 subtask 里塞多步。
- 如果 worker 的输出已经覆盖原始任务的所有需求,选 DONE。
- subtask 不要直接复述原始任务,要细化到 worker 角色。

只输出 JSON,不要 markdown 包裹,不要其他说明。"""

SYNTHESIZER_PROMPT = """你是合成器,负责把多个 worker 的产出汇总成给用户的最终回答。

【用户原始任务】
{task}

【各 worker 的子任务与产出】
{outputs}

请给出**自然、简洁**的最终答案。如果用户任务里指定了输出格式(JSON、表格等),严格按格式输出。
不要再解释 worker 是谁、流程是什么,直接给最终结果。"""


@dataclass
class MultiConfig:
    model: str
    max_rounds: int = 6


class MultiAgentSystem:
    def __init__(self, config: MultiConfig | None = None, tracer=None):
        # 如果传入 tracer,用 traced httpx — 内部 supervisor / worker / synthesizer
        # 的所有 LLM 调用都会被 outer 的 trace 捕获(支持 Agent-as-Tool 嵌套追踪)
        if tracer is not None:
            from tracing_http import make_traced_openai

            self.client = make_traced_openai(tracer)
        else:
            self.client = OpenAI()
        self.tracer = tracer
        self.config = config or MultiConfig(
            model=os.getenv("AGENT_MODEL", "gpt-4.1-mini"),
            max_rounds=int(os.getenv("AGENT_MAX_STEPS", "6")),
        )
        self.app = self._build_graph()

    # ------------------------------------------------------------------

    def run(self, task: str) -> str:
        print(f"\n{C.BOLD}{C.CYAN}USER ▶{C.RESET}{C.DIM} [MULTI-AGENT]{C.RESET} {task}")
        t0 = time.perf_counter()
        state: MultiState = {
            "task": task,
            "worker_outputs": [],
            "rounds": 0,
        }
        result = self.app.invoke(state, {"recursion_limit": self.config.max_rounds * 4})
        elapsed = time.perf_counter() - t0
        answer = result.get("final_answer", "(没有得到 final_answer)")
        print(f"\n{C.BOLD}{C.GREEN}AGENT ▶{C.RESET} {answer}")
        print(
            f"{C.DIM}══ Total ══ rounds={result.get('rounds', 0)} "
            f"workers_used={len(result.get('worker_outputs', []))} elapsed={elapsed:.2f}s{C.RESET}\n"
        )
        return answer

    # ------------------------------------------------------------------
    # 节点
    # ------------------------------------------------------------------

    def _supervisor(self, state: MultiState) -> dict:
        if self.tracer is not None:
            self.tracer.push_actor("supervisor")
        try:
            return self._supervisor_inner(state)
        finally:
            if self.tracer is not None:
                self.tracer.pop_actor()

    def _supervisor_inner(self, state: MultiState) -> dict:
        roster = "\n".join(f"- {w.name}: {w.description}" for w in WORKERS.values())
        names = list(WORKERS.keys()) + ["DONE"]
        past = (
            "\n".join(
                f"- [{o['worker']}] subtask: {o['subtask']}\n  output: {o['output']}"
                for o in state.get("worker_outputs", [])
            )
            or "(暂无)"
        )

        prompt = SUPERVISOR_PROMPT.format(
            roster=roster, task=state["task"], past=past, names=names
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as exc:
            data = {"next_worker": "DONE", "subtask": f"(supervisor 异常: {exc})"}

        nxt = str(data.get("next_worker", "DONE"))
        subtask = str(data.get("subtask", ""))

        # 保护:超过最大轮数或路由非法 → 强制 DONE
        rounds = state.get("rounds", 0) + 1
        if nxt not in WORKERS and nxt != "DONE":
            nxt = "DONE"
        if rounds > self.config.max_rounds:
            nxt = "DONE"

        print(
            f"\n{C.BOLD}{C.BLUE}── Supervisor (round {rounds}) ──{C.RESET} "
            f"→ {C.BOLD}{nxt}{C.RESET}"
        )
        if nxt != "DONE":
            print(f"  subtask: {subtask}")

        return {
            "next_worker": nxt,
            "current_subtask": subtask,
            "rounds": rounds,
        }

    def _make_worker_node(self, worker_name: str):
        def node(state: MultiState) -> dict:
            worker = WORKERS[worker_name]
            output = worker.run(
                state["current_subtask"], self.client, self.config.model, tracer=self.tracer
            )
            outputs = list(state.get("worker_outputs", []))
            outputs.append(
                {
                    "worker": worker_name,
                    "subtask": state["current_subtask"],
                    "output": output,
                }
            )
            return {"worker_outputs": outputs}

        return node

    def _synthesizer(self, state: MultiState) -> dict:
        if self.tracer is not None:
            self.tracer.push_actor("synthesizer")
        try:
            return self._synthesizer_inner(state)
        finally:
            if self.tracer is not None:
                self.tracer.pop_actor()

    def _synthesizer_inner(self, state: MultiState) -> dict:
        outputs_block = (
            "\n".join(
                f"### [{o['worker']}] subtask: {o['subtask']}\n{o['output']}"
                for o in state.get("worker_outputs", [])
            )
            or "(没有 worker 产出)"
        )
        prompt = SYNTHESIZER_PROMPT.format(task=state["task"], outputs=outputs_block)
        resp = self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        answer = (resp.choices[0].message.content or "").strip()
        print(f"\n{C.BOLD}{C.GREEN}── Synthesizer ──{C.RESET}")
        return {"final_answer": answer}

    # ------------------------------------------------------------------

    def _route_after_supervisor(self, state: MultiState) -> str:
        nxt = state.get("next_worker", "DONE")
        if nxt == "DONE":
            return "synthesizer"
        return nxt

    def _build_graph(self):
        graph = StateGraph(MultiState)
        graph.add_node("supervisor", self._supervisor)
        for name in WORKERS:
            graph.add_node(name, self._make_worker_node(name))
        graph.add_node("synthesizer", self._synthesizer)

        graph.set_entry_point("supervisor")
        graph.add_conditional_edges(
            "supervisor",
            self._route_after_supervisor,
            {**{name: name for name in WORKERS}, "synthesizer": "synthesizer"},
        )
        for name in WORKERS:
            graph.add_edge(name, "supervisor")
        graph.add_edge("synthesizer", END)
        return graph.compile()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def main() -> None:
    _ensure_utf8_stdout()
    load_dotenv()

    if len(sys.argv) < 2:
        print("用法: python agent_multi.py \"<task>\"")
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    system = MultiAgentSystem()
    system.run(task)


if __name__ == "__main__":
    main()
