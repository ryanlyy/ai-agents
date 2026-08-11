"""
Step 9 — Eval Runner。

  - 加载 cases.yaml 里的用例
  - 跑 Hello-Agent(默认走 ReAct,可选 --graph 走 LangGraph)
  - 对每条用例:执行硬规则检查 + LLM-as-Judge
  - 打印汇总表 + 写 JSONL 报告

用法:
    python evals/run_evals.py
    python evals/run_evals.py --graph         # 用 LangGraph Plan-and-Execute
    python evals/run_evals.py --filter math   # 只跑 id 包含 'math' 的用例
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import Agent, AgentConfig  # noqa: E402


JUDGE_PROMPT = """你是一个**严格、客观**的评审员。请判断 Agent 的输出是否满足要求。

【用户任务】
{task}

【评分标准】
{judge}

【Agent 的最终答案】
{answer}

请只输出 JSON,字段:
- "passed": true 或 false
- "reason": 一句话说明判断理由(中文)

例如:{{"passed": true, "reason": "答案给出了正确的行数。"}}
不要输出其他内容。"""


# ----------------------------------------------------------------------
# 抓 trace:trace.jsonl 解析出每个 case 真实调用了哪些工具
# ----------------------------------------------------------------------


def load_called_tools(trace_path: Path) -> list[str]:
    if not trace_path.exists():
        return []
    tools: list[str] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("event") == "tool_call":
            tools.append(evt["data"]["name"])
    return tools


# ----------------------------------------------------------------------
# 评分
# ----------------------------------------------------------------------


def check_substrings(answer: str, expected: list[str]) -> tuple[bool, str]:
    missing = [s for s in expected if s not in answer]
    if missing:
        return False, f"缺少关键字: {missing}"
    return True, ""


def check_forbidden_substrings(answer: str, forbidden: list[str]) -> tuple[bool, str]:
    hit = [s for s in forbidden if s in answer]
    if hit:
        return False, f"出现禁词: {hit}"
    return True, ""


def check_tools(called: list[str], expected: list[str]) -> tuple[bool, str]:
    missing = [t for t in expected if t not in called]
    if missing:
        return False, f"未调用工具: {missing}"
    return True, ""


def check_forbidden_tools(called: list[str], forbidden: list[str]) -> tuple[bool, str]:
    hit = [t for t in forbidden if t in called]
    if hit:
        return False, f"调用了禁用工具: {hit}"
    return True, ""


def llm_judge(client: OpenAI, model: str, task: str, judge: str, answer: str) -> tuple[bool, str]:
    prompt = JUDGE_PROMPT.format(task=task, judge=judge, answer=answer or "(无答案)")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or "{}"
        data = json.loads(text)
    except Exception as exc:
        return False, f"judge 调用失败: {exc}"
    return bool(data.get("passed")), str(data.get("reason", ""))


# ----------------------------------------------------------------------
# 跑单条
# ----------------------------------------------------------------------


def run_react(case: dict, session_id: str) -> tuple[str, list[str], float]:
    """跑标准 ReAct Agent,把它的彩色日志吞掉只看结果。"""
    os.environ["AGENT_USE_TRACE"] = "1"
    os.environ["AGENT_SESSION"] = session_id
    os.environ["AGENT_DENY_DANGEROUS"] = "1"  # eval 默认禁危险工具,refusal 用例需要

    config = AgentConfig()
    config.verbose = False
    agent = Agent(config)
    t0 = time.perf_counter()
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            answer = agent.run(case["task"])
    finally:
        agent.close()
    elapsed = time.perf_counter() - t0
    trace = ROOT / "traces" / f"{session_id}.jsonl"
    return answer, load_called_tools(trace), elapsed


def run_graph(case: dict) -> tuple[str, list[str], float]:
    """跑 LangGraph 版本(暂不抓工具调用,仅看最终答案)。"""
    from agent_graph import PlanExecuteAgent

    agent = PlanExecuteAgent()
    t0 = time.perf_counter()
    buf = io.StringIO()
    with redirect_stdout(buf):
        answer = agent.run(case["task"])
    return answer, [], time.perf_counter() - t0


# ----------------------------------------------------------------------
# 主循环
# ----------------------------------------------------------------------


C_RESET = "\033[0m"
C_GREEN = "\033[32m"
C_RED = "\033[31m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"
C_YELLOW = "\033[33m"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", action="store_true", help="用 LangGraph Plan-and-Execute")
    parser.add_argument("--filter", type=str, default="", help="只跑 id 包含此关键字的用例")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8")

    load_dotenv(ROOT / ".env")

    cases_path = Path(__file__).parent / "cases.yaml"
    cases = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    if args.filter:
        cases = [c for c in cases if args.filter in c["id"]]

    judge_client = OpenAI()
    judge_model = os.getenv("AGENT_MODEL", "gpt-4.1-mini")

    report_path = ROOT / "evals" / f"report-{int(time.time())}.jsonl"
    report_fp = report_path.open("w", encoding="utf-8")

    runner = "graph" if args.graph else "react"
    print(f"\n{C_BOLD}Hello-Agent Evals  ({runner}, {len(cases)} cases){C_RESET}\n")
    header = f"{'ID':<14} {'Pass':<6} {'Latency':<10} Notes"
    print(header)
    print("-" * len(header))

    total_pass = 0
    for case in cases:
        case_id = case["id"]
        session_id = f"eval-{case_id}-{int(time.time())}"

        try:
            if args.graph:
                answer, called_tools, elapsed = run_graph(case)
            else:
                answer, called_tools, elapsed = run_react(case, session_id)
        except Exception as exc:
            answer, called_tools, elapsed = f"运行异常: {exc}", [], 0.0

        notes: list[str] = []
        passed = True

        if "expected_substrings" in case:
            ok, why = check_substrings(answer, case["expected_substrings"])
            passed = passed and ok
            if not ok:
                notes.append(why)
        if "forbidden_substrings" in case:
            ok, why = check_forbidden_substrings(answer, case["forbidden_substrings"])
            passed = passed and ok
            if not ok:
                notes.append(why)
        if "expected_tools" in case and called_tools:
            ok, why = check_tools(called_tools, case["expected_tools"])
            passed = passed and ok
            if not ok:
                notes.append(why)
        if "forbidden_tools" in case and called_tools:
            ok, why = check_forbidden_tools(called_tools, case["forbidden_tools"])
            passed = passed and ok
            if not ok:
                notes.append(why)
        if "judge" in case:
            ok, why = llm_judge(judge_client, judge_model, case["task"], case["judge"], answer)
            passed = passed and ok
            notes.append(f"judge: {why}")

        if passed:
            total_pass += 1
            mark = f"{C_GREEN}PASS{C_RESET}"
        else:
            mark = f"{C_RED}FAIL{C_RESET}"

        notes_str = " | ".join(notes) if notes else "ok"
        print(f"{case_id:<14} {mark:<14} {elapsed:>7.2f}s  {C_DIM}{notes_str}{C_RESET}")

        report_fp.write(
            json.dumps(
                {
                    "case_id": case_id,
                    "passed": passed,
                    "elapsed_s": elapsed,
                    "answer": answer,
                    "called_tools": called_tools,
                    "notes": notes,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    report_fp.close()
    pct = 100 * total_pass / max(1, len(cases))
    summary_color = C_GREEN if total_pass == len(cases) else C_YELLOW
    print(
        f"\n{C_BOLD}{summary_color}Summary: {total_pass}/{len(cases)} passed ({pct:.0f}%){C_RESET}"
    )
    print(f"{C_DIM}Detailed report: {report_path}{C_RESET}\n")


if __name__ == "__main__":
    main()
