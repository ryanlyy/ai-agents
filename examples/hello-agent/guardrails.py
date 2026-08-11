"""
Step 7 — Guardrails(护栏)。

提供三道防线:
  1. **危险工具人工审批**:`tools.DANGEROUS_TOOLS` 里的工具被调用前会询问。
                          - TTY:交互问 [y/N]
                          - 非交互或 AGENT_AUTO_APPROVE=1:按设置自动放行/拒绝
  2. **token 上限**:跑超 MAX_TOTAL_TOKENS 时,Agent 立即终止循环。
  3. **成本上限**:配合 PRICE_*,超 MAX_COST_USD 立即终止。

所有判断都是纯函数,易测易扩展。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass


def _envflag(name: str, default: str = "") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _envfloat(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class GuardrailsConfig:
    auto_approve: bool = False
    deny_dangerous: bool = False
    max_total_tokens: int = 0  # 0 = 不限
    max_cost_usd: float = 0.0
    price_prompt_per_1m: float = 0.0
    price_completion_per_1m: float = 0.0

    @classmethod
    def from_env(cls) -> "GuardrailsConfig":
        return cls(
            auto_approve=_envflag("AGENT_AUTO_APPROVE"),
            deny_dangerous=_envflag("AGENT_DENY_DANGEROUS"),
            max_total_tokens=int(_envfloat("MAX_TOTAL_TOKENS", 0)),
            max_cost_usd=_envfloat("MAX_COST_USD", 0.0),
            price_prompt_per_1m=_envfloat("PRICE_PROMPT_USD_PER_1M", 0.0),
            price_completion_per_1m=_envfloat("PRICE_COMPLETION_USD_PER_1M", 0.0),
        )


class Budget:
    """累计 token 与成本,超额返回 (True, 原因)。"""

    def __init__(self, cfg: GuardrailsConfig):
        self.cfg = cfg
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cost_usd = 0.0

    def record_llm(self, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += total_tokens
        self.cost_usd += (
            prompt_tokens * self.cfg.price_prompt_per_1m / 1_000_000
            + completion_tokens * self.cfg.price_completion_per_1m / 1_000_000
        )

    def exceeded(self) -> tuple[bool, str]:
        if self.cfg.max_total_tokens and self.total_tokens >= self.cfg.max_total_tokens:
            return True, f"总 token 数 {self.total_tokens} 已达上限 {self.cfg.max_total_tokens}"
        if self.cfg.max_cost_usd and self.cost_usd >= self.cfg.max_cost_usd:
            return True, f"成本 ${self.cost_usd:.4f} 已达上限 ${self.cfg.max_cost_usd}"
        return False, ""

    def summary(self) -> str:
        return (
            f"tokens={self.total_tokens} "
            f"(prompt={self.prompt_tokens}, completion={self.completion_tokens}) "
            f"cost=${self.cost_usd:.4f}"
        )


class Approver:
    """决定危险工具是否放行。"""

    def __init__(self, cfg: GuardrailsConfig):
        self.cfg = cfg

    def approve(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        # 显式拒绝优先级最高
        if self.cfg.deny_dangerous:
            return False, "策略已禁止运行危险工具(AGENT_DENY_DANGEROUS=1)。"

        # 自动放行
        if self.cfg.auto_approve:
            return True, "auto-approved"

        # 非交互终端 → 默认拒绝(让 LLM 知道并改路径)
        if not sys.stdin.isatty():
            return False, "非交互模式且未设置 AGENT_AUTO_APPROVE,默认拒绝危险操作。"

        # 交互终端 → 询问
        args_repr = json.dumps(arguments, ensure_ascii=False)
        prompt = (
            f"\n⚠️  Agent 想要执行危险工具:{tool_name}({args_repr})\n"
            f"是否允许?[y/N]: "
        )
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            return False, "stdin EOF,默认拒绝。"
        if answer in {"y", "yes"}:
            return True, "用户已批准"
        return False, "用户拒绝执行"
