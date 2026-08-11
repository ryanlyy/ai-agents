"""LangGraph Plan-and-Execute 入口(对照 main.py 的 ReAct 版本)。"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from agent_graph import PlanExecuteAgent


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

    agent = PlanExecuteAgent()

    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        agent.run(task)
        return

    print("Plan-and-Execute Graph 交互模式。输入 'exit' 退出。\n")
    while True:
        try:
            task = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not task:
            continue
        if task.lower() in {"exit", "quit", ":q"}:
            break
        agent.run(task)


if __name__ == "__main__":
    main()
