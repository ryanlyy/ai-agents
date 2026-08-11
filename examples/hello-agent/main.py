"""
命令行入口。

用法:
  python main.py "你的问题"        # 单次任务
  python main.py                   # 交互模式

环境变量(写在 .env 即可):
  AGENT_USE_MCP=1     工具走 MCP Server
  AGENT_USE_MEMORY=1  开启 SQLite + 向量记忆
  AGENT_USE_TRACE=1   写 traces/<session>.jsonl(若 LANGFUSE_* 设了同时上报)
  AGENT_SESSION=xxxx  指定会话 id(默认每次随机)
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from agent import Agent, AgentConfig


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

    agent = Agent(AgentConfig())

    try:
        if len(sys.argv) > 1:
            task = " ".join(sys.argv[1:])
            agent.run(task)
            return

        print("Hello-Agent 交互模式。输入 'exit' 或 Ctrl+C 退出。\n")
        base_session = agent.session_id
        turn = 0
        while True:
            try:
                task = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见。")
                break
            if not task:
                continue
            if task.lower() in {"exit", "quit", ":q"}:
                print("再见。")
                break

            turn += 1
            # 交互模式下,每轮 chat 写到独立 trace 文件:<base>-<turn>.jsonl
            if agent._tracer is not None:
                agent._tracer.rotate(f"{base_session}-{turn:03d}")

            agent.run(task)
    finally:
        agent.close()


if __name__ == "__main__":
    main()
