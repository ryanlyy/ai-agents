"""
Reflexion(Shinn et al. 2023)的最小实现。

设计要点:
  Reflexion 是一种 **meta 模式**,可以套在任何 base agent 外面。
  它不替换 ReAct,而是把 ReAct 的一次输出当作"草稿":
    1. Executor:跑一次完整的 base agent(默认 ReAct)。
    2. Evaluator:LLM-as-Judge 判断这次答案是否过关 + 给出失败原因。
    3. Reflect:如果失败,把"教训"翻译成下一次的指导语。
    4. 重试:把累计的所有教训拼成 system 注入,再跑一次 Executor。

经典的 Reflexion 闭环就是:Action → Evaluation → Reflection → Retry。
我们这里把 base agent 当成"Action 阶段"。
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI

from agent import Agent, AgentConfig


# -----------------------------------------------------------------------------
# Prompts
# -----------------------------------------------------------------------------

EVALUATOR_PROMPT = """你是一个**严格、客观**的评审员。
判断 Agent 的回答是否完全满足以下要求:

【用户原始任务】
{task}

【评审准则】
{rubric}

【Agent 当前的回答】
{answer}

请输出严格的 JSON,字段:
- "passed": true 或 false
- "reason": 一句话说明判断理由(中文)。如果失败,具体指出哪里不符合。

只输出 JSON,不要其他内容。"""

REFLECT_PROMPT = """你是一个反思助手。一个 Agent 刚刚完成了任务,但评审员判定**未通过**。
请把失败原因转化为对 Agent 下一次尝试的**简短指令**(1-2 句),让它能避免同样错误。

【用户原始任务】
{task}

【失败的回答】
{answer}

【评审失败原因】
{reason}

请只输出一句**第二人称的指令**(以"下次:"开头),例如:
- "下次:不要在 JSON 外面包 markdown 代码块。"
- "下次:必须包含 nyc_time 字段。"

不要输出其他内容。"""


# -----------------------------------------------------------------------------
# 数据结构
# -----------------------------------------------------------------------------


@dataclass
class Attempt:
    answer: str
    passed: bool
    reason: str
    lesson: str | None  # reflect 出来的下一次指令


@dataclass
class ReflexionConfig:
    rubric: str
    max_iterations: int = 3
    judge_model: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", "gpt-4.1-mini"))


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


# -----------------------------------------------------------------------------
# ReflexionAgent
# -----------------------------------------------------------------------------


class ReflexionAgent:
    """套在任意 base agent 外面的 Reflexion 包装器。"""

    def __init__(self, config: ReflexionConfig, base_agent: Agent | None = None):
        self.config = config
        self.judge = OpenAI()
        self._owns_base = base_agent is None
        if base_agent is None:
            base_cfg = AgentConfig()
            base_cfg.verbose = False  # base agent 静默,日志由 Reflexion 控制
            base_agent = Agent(base_cfg)
        self.base = base_agent

    # ------------------------------------------------------------------

    def run(self, task: str) -> Attempt:
        print(f"\n{C.BOLD}{C.CYAN}USER ▶{C.RESET}{C.DIM} [REFLEXION rubric=\"{self.config.rubric[:60]}…\"]{C.RESET} {task}")

        attempts: list[Attempt] = []
        lessons: list[str] = []
        run_started = time.perf_counter()

        for i in range(1, self.config.max_iterations + 1):
            print(
                f"\n{C.BOLD}{C.BLUE}══ Attempt {i}/{self.config.max_iterations} ══{C.RESET}"
            )

            # 把已有教训拼成 reflexion memo,塞给 base agent
            augmented_task = task
            if lessons:
                memo = "\n".join(f"- {ln}" for ln in lessons)
                augmented_task = (
                    f"{task}\n\n"
                    f"## 来自上次失败的反思(必须遵守)\n{memo}"
                )

            answer = self.base.run(augmented_task)
            print(f"{C.MAGENTA}Answer     :{C.RESET} {self._snippet(answer)}")

            verdict = self._evaluate(task, answer)
            mark = (
                f"{C.GREEN}PASS{C.RESET}" if verdict["passed"] else f"{C.RED}FAIL{C.RESET}"
            )
            print(f"{C.YELLOW}Evaluator  :{C.RESET} {mark} — {verdict['reason']}")

            if verdict["passed"]:
                attempts.append(
                    Attempt(answer=answer, passed=True, reason=verdict["reason"], lesson=None)
                )
                self._log_done(attempts, time.perf_counter() - run_started)
                return attempts[-1]

            # 失败:反思,产出下次的 lesson
            lesson = self._reflect(task, answer, verdict["reason"])
            print(f"{C.DIM}Reflect    : {lesson}{C.RESET}")
            lessons.append(lesson)
            attempts.append(
                Attempt(answer=answer, passed=False, reason=verdict["reason"], lesson=lesson)
            )

        # 所有尝试都失败,返回最后一次
        last = attempts[-1]
        self._log_done(attempts, time.perf_counter() - run_started)
        return last

    def close(self) -> None:
        if self._owns_base:
            self.base.close()

    # ------------------------------------------------------------------

    def _evaluate(self, task: str, answer: str) -> dict:
        prompt = EVALUATOR_PROMPT.format(
            task=task, rubric=self.config.rubric, answer=answer or "(无答案)"
        )
        try:
            resp = self.judge.chat.completions.create(
                model=self.config.judge_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            return {
                "passed": bool(data.get("passed")),
                "reason": str(data.get("reason", "")),
            }
        except Exception as exc:
            return {"passed": False, "reason": f"evaluator 调用失败: {exc}"}

    def _reflect(self, task: str, answer: str, reason: str) -> str:
        prompt = REFLECT_PROMPT.format(task=task, answer=answer or "(无答案)", reason=reason)
        try:
            resp = self.judge.chat.completions.create(
                model=self.config.judge_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            return f"下次:针对评审失败原因({reason})做相应调整。[reflect 异常: {exc}]"

    # ------------------------------------------------------------------

    @staticmethod
    def _snippet(text: str, n: int = 240) -> str:
        text = text.strip().replace("\n", " ")
        return text if len(text) <= n else text[:n] + "…"

    def _log_done(self, attempts: list[Attempt], elapsed: float) -> None:
        passed = attempts[-1].passed
        color = C.GREEN if passed else C.RED
        head = "FINAL (PASSED)" if passed else "FINAL (FAILED, returning last attempt)"
        print(f"\n{C.BOLD}{color}══ {head} ══{C.RESET} 共 {len(attempts)} 次尝试,{elapsed:.2f}s")
        print(f"{C.BOLD}{C.GREEN}AGENT ▶{C.RESET} {attempts[-1].answer}\n")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


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
        print(
            "用法: python agent_reflexion.py \"<task>\" [--rubric \"<rubric>\"] [--max N]"
        )
        sys.exit(1)

    args = sys.argv[1:]
    task: str | None = None
    rubric: str = (
        "答案应当满足任务要求。如果任务里指定了输出格式(如 JSON),"
        "答案必须严格符合该格式,不能有多余的 markdown 包装、注释、解释。"
    )
    max_iter = 3

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--rubric" and i + 1 < len(args):
            rubric = args[i + 1]
            i += 2
        elif a == "--max" and i + 1 < len(args):
            max_iter = int(args[i + 1])
            i += 2
        else:
            task = (task + " " if task else "") + a
            i += 1

    if not task:
        print("缺少 task。")
        sys.exit(1)

    cfg = ReflexionConfig(rubric=rubric, max_iterations=max_iter)
    agent = ReflexionAgent(cfg)
    try:
        agent.run(task)
    finally:
        agent.close()


if __name__ == "__main__":
    main()
