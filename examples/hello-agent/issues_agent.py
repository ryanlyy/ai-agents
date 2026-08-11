"""
Issues-Agent:自动收集 https://github.com/kubernetes/kubernetes 的 reported issue,
生成以时间命名的 Markdown 报告。

三种触发模式
------------
  1. 手动触发(once)    :跑一次后退出。
  2. 指令触发(serve)   :启动 HTTP 服务 + 浏览器 UI
                          - `GET  /`                浏览器查看 + 触发按钮
                          - `POST /api/trigger`     远程触发一次抓取(202 立即返回)
                          - `GET  /api/status`      当前状态(busy / last_run / base_config)
                          - `GET  /api/reports`     列出 `reports/k8s-issues-*.md`
                          - `GET  /api/reports/{name}`  返回单个报告原文(text/markdown)
                          - `GET  /health`          健康检查
                          为兼容,`POST /trigger` 也指向同一处理器。
  3. 定时触发(schedule):按 --interval 秒周期性触发。

代理支持
--------
解析顺序(优先级从高到低):
  1. CLI --proxy URL
  2. 环境变量 ISSUES_PROXY
  3. 环境变量 HTTPS_PROXY / HTTP_PROXY(httpx trust_env)
  4. --proxy-default → 落到内置默认 http://10.158.100.2:8080

注意:仅出公网(GitHub API)走代理;若同时跑可选的 LLM 概述且 LLM 在内网,
请在 .env 里的 NO_PROXY 包含 LLM 主机,httpx 会自动绕过。

依赖
----
仅 httpx + python-dotenv(已在 requirements.txt 里)。LLM 概述与 HTTP 服务为可选,
分别需要 openai 与 starlette+uvicorn(都已经被现有依赖间接装好)。

报告输出
--------
默认是 **LLM 分析模式**:抓取后,挑最近活跃的 50 条 issue,用 LLM 输出
三段式 markdown 报告:
  1. Issue 总览(Themes)        —— 主题、热点 area/sig、严重度趋势
  2. 对应用团队的影响(App)     —— 工作负载/网络/存储/API 兼容性 视角
  3. 对 CaaS 平台团队的影响(CaaS)—— 控制面/节点/升级/安全/扩展性 视角
报告末尾附 _Evidence_ 表,列出 LLM 用到的 issue 编号 → URL 对照。

加 `--no-llm` 或 LLM 不可用时,自动 fallback 到 Top-N 客观列表。

CLI 示例
--------
  # 手动触发,默认 LLM 三段式分析(用 .env 里的 OpenAI / Ollama)
  python issues_agent.py once

  # 不用 LLM,只列 Top-N
  python issues_agent.py once --no-llm

  # 显式代理 + 走 closed issues 的最近一段
  python issues_agent.py once --proxy http://10.158.100.2:8080 \
      --state closed --since 2026-04-01T00:00:00Z --max-pages 5

  # 定时:每 30 分钟跑一次
  python issues_agent.py schedule --interval 1800

  # HTTP 指令 + 浏览器 UI:监听 9090,带 token 鉴权
  python issues_agent.py serve --port 9090 --token my-secret
  # 浏览器打开 http://127.0.0.1:9090
  # 命令行触发(显式关掉 LLM):
  curl -X POST http://127.0.0.1:9090/api/trigger \
       -H "X-Trigger-Token: my-secret" \
       -H "Content-Type: application/json" \
       -d '{"state":"open","max_pages":2,"use_llm":false}'
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv


REPO = "kubernetes/kubernetes"
GITHUB_API = "https://api.github.com"
DEFAULT_PROXY = "http://10.158.100.2:8080"


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


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# =============================================================================
# 配置
# =============================================================================


@dataclass
class IssuesAgentConfig:
    repo: str = REPO
    state: str = "open"  # open / closed / all
    since: str | None = None  # ISO-8601,例如 "2026-04-01T00:00:00Z"
    labels: list[str] = field(default_factory=list)
    max_pages: int = 0  # 0 = 不限
    max_issues: int = 0  # 0 = 不限
    per_page: int = 100
    proxy: str | None = None  # 显式代理;None → 走 httpx trust_env
    github_token: str | None = None
    timeout_s: float = 30.0
    out_dir: Path = field(default_factory=lambda: Path("reports"))
    # 默认开启 LLM 分析:报告主体是"主题总览 + 对应用的影响 + 对 CaaS 的影响"。
    # 若 LLM 不可用,会自动 fallback 到 Top-N 列表(并在报告里标注)。
    use_llm: bool = True
    model: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", "gpt-4.1-mini"))
    top_n_listed: int = 50
    verbose: bool = True


# =============================================================================
# Agent 主体
# =============================================================================


class IssuesAgent:
    """收集 issue → 统计 → (可选 LLM 概述)→ 写报告。"""

    def __init__(self, config: IssuesAgentConfig | None = None):
        self.cfg = config or IssuesAgentConfig()
        self.cfg.out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 主入口 ----------

    def run(self) -> Path:
        t0 = time.perf_counter()
        self._log(
            f"[fetch] repo={self.cfg.repo} state={self.cfg.state} "
            f"since={self.cfg.since or '-'} labels={self.cfg.labels or '-'} "
            f"proxy={'explicit' if self.cfg.proxy else 'env'} "
            f"token={'yes' if self.cfg.github_token else 'no'}",
            color=C.CYAN,
        )
        issues = self._fetch_all_issues()
        elapsed_fetch = time.perf_counter() - t0

        self._log(f"[fetch] got {len(issues)} issues in {elapsed_fetch:.1f}s", color=C.GREEN)

        stats = self._compute_stats(issues)

        llm_analysis: str | None = None
        evidence: list[dict] = []
        if self.cfg.use_llm:
            llm_analysis, evidence = self._llm_analysis(issues, stats)

        path = self._write_report(issues, stats, llm_analysis, evidence, elapsed_fetch)
        self._log(f"[done] report → {path}", color=C.GREEN)
        return path

    # ---------- HTTP 客户端 ----------

    def _http_client(self) -> httpx.Client:
        kwargs: dict = {
            "timeout": self.cfg.timeout_s,
            "follow_redirects": True,
            "trust_env": True,  # 不显式 proxy 时,自动 pick up HTTPS_PROXY
        }
        if self.cfg.proxy:
            kwargs["proxy"] = self.cfg.proxy

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hello-agent-issues-collector/1.0",
        }
        if self.cfg.github_token:
            headers["Authorization"] = f"Bearer {self.cfg.github_token}"
        kwargs["headers"] = headers

        return httpx.Client(**kwargs)

    # ---------- 抓取 ----------

    def _fetch_all_issues(self) -> list[dict]:
        url = f"{GITHUB_API}/repos/{self.cfg.repo}/issues"
        params: dict[str, str] = {
            "state": self.cfg.state,
            "per_page": str(self.cfg.per_page),
            "sort": "updated",
            "direction": "desc",
        }
        if self.cfg.since:
            params["since"] = self.cfg.since
        if self.cfg.labels:
            params["labels"] = ",".join(self.cfg.labels)

        all_issues: list[dict] = []
        page = 1

        with self._http_client() as client:
            while True:
                page_params = dict(params, page=str(page))
                t0 = time.perf_counter()
                try:
                    r = client.get(url, params=page_params)
                except httpx.RequestError as exc:
                    self._log(f"[fetch] page {page} 网络错误: {exc}", color=C.RED)
                    break
                latency = time.perf_counter() - t0

                if r.status_code == 401:
                    self._log(
                        "[fetch] 401 unauthorized — 请检查 GITHUB_TOKEN 是否有效",
                        color=C.RED,
                    )
                    break
                if r.status_code == 403:
                    rl = r.headers.get("X-RateLimit-Remaining", "?")
                    reset = r.headers.get("X-RateLimit-Reset", "?")
                    self._log(
                        f"[fetch] 403 rate-limited remaining={rl} reset={reset} "
                        f"(unauth 60/h,建议设 GITHUB_TOKEN 提升到 5000/h)",
                        color=C.RED,
                    )
                    break
                if r.status_code >= 400:
                    self._log(
                        f"[fetch] HTTP {r.status_code}: {r.text[:200]}", color=C.RED
                    )
                    break

                try:
                    batch = r.json() or []
                except ValueError:
                    self._log("[fetch] response 不是合法 JSON", color=C.RED)
                    break

                # GitHub Issues API 把 PR 也算 issue,带 pull_request 字段,过滤掉
                only_issues = [it for it in batch if "pull_request" not in it]
                all_issues.extend(only_issues)
                rl_remaining = r.headers.get("X-RateLimit-Remaining", "?")

                self._log(
                    f"[fetch] page {page}: +{len(only_issues)} issues "
                    f"(PRs filtered={len(batch) - len(only_issues)}) "
                    f"rate-remaining={rl_remaining} ({latency:.2f}s)"
                )

                if not batch or len(batch) < self.cfg.per_page:
                    break
                if self.cfg.max_pages and page >= self.cfg.max_pages:
                    self._log(f"[fetch] 达到 max_pages={self.cfg.max_pages},停止")
                    break
                if self.cfg.max_issues and len(all_issues) >= self.cfg.max_issues:
                    all_issues = all_issues[: self.cfg.max_issues]
                    self._log(f"[fetch] 达到 max_issues={self.cfg.max_issues},停止")
                    break
                page += 1

        return all_issues

    # ---------- 统计 ----------

    def _compute_stats(self, issues: list[dict]) -> dict:
        by_state: Counter[str] = Counter()
        label_counter: Counter[str] = Counter()
        assignee_counter: Counter[str] = Counter()
        author_counter: Counter[str] = Counter()
        for it in issues:
            by_state[it.get("state") or "?"] += 1
            for lbl in it.get("labels") or []:
                name = lbl.get("name") if isinstance(lbl, dict) else str(lbl)
                if name:
                    label_counter[name] += 1
            for a in it.get("assignees") or []:
                login = (a or {}).get("login")
                if login:
                    assignee_counter[login] += 1
            user = (it.get("user") or {}).get("login")
            if user:
                author_counter[user] += 1

        # 按 updated_at 分桶
        now = datetime.now(timezone.utc)
        buckets: Counter[str] = Counter()
        for it in issues:
            updated = it.get("updated_at")
            if not updated:
                buckets["unknown"] += 1
                continue
            try:
                ts = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                buckets["unknown"] += 1
                continue
            age = now - ts
            if age <= timedelta(hours=24):
                buckets["<=24h"] += 1
            elif age <= timedelta(days=7):
                buckets["<=7d"] += 1
            elif age <= timedelta(days=30):
                buckets["<=30d"] += 1
            else:
                buckets["older"] += 1

        return {
            "total": len(issues),
            "by_state": dict(by_state),
            "top_labels": label_counter.most_common(15),
            "top_assignees": assignee_counter.most_common(10),
            "top_authors": author_counter.most_common(10),
            "activity_buckets": dict(buckets),
        }

    # ---------- LLM 分析(三段式) ----------

    # 单次喂给 LLM 的 issue 样本上限。每条 ~500 字符(title+labels+body 摘要),
    # 默认 50 条 ≈ 6-8k tokens,gpt-4.1-mini / gpt-oss:20b 都吃得下。
    _LLM_SAMPLE_SIZE = 50
    _LLM_BODY_CHARS = 280

    def _build_issue_sample_block(self, issues: list[dict]) -> tuple[str, list[dict]]:
        """挑选最近活跃的 N 个 issue,渲染成喂给 LLM 的紧凑列表。

        返回 (markdown_block, sampled_issues_meta)
        """
        sample = issues[: self._LLM_SAMPLE_SIZE]
        rows: list[str] = []
        meta: list[dict] = []
        for it in sample:
            num = it.get("number")
            title = (it.get("title") or "").replace("\n", " ").strip()
            if len(title) > 140:
                title = title[:137] + "..."
            label_names = [
                lbl.get("name") if isinstance(lbl, dict) else str(lbl)
                for lbl in (it.get("labels") or [])
            ]
            label_names = [n for n in label_names if n]
            labels_str = "+".join(label_names[:5]) or "-"
            body = (it.get("body") or "").replace("\r", " ").replace("\n", " ").strip()
            if len(body) > self._LLM_BODY_CHARS:
                body = body[: self._LLM_BODY_CHARS] + "..."
            comments = it.get("comments", 0)
            state = it.get("state", "?")
            rows.append(
                f"- #{num} [{state} | {labels_str} | {comments}c] {title}\n"
                f"  body: {body or '(empty)'}"
            )
            meta.append(
                {
                    "number": num,
                    "title": title,
                    "labels": label_names,
                    "url": it.get("html_url", ""),
                    "updated_at": it.get("updated_at", ""),
                    "state": state,
                }
            )
        return "\n".join(rows), meta

    def _llm_analysis(
        self, issues: list[dict], stats: dict
    ) -> tuple[str | None, list[dict]]:
        """生成三段式 markdown 分析:Themes / Impact on App / Impact on CaaS。

        返回 (markdown_str_or_None, evidence_meta_list)。失败时 markdown 为 None,
        但 evidence_meta 仍会返回(供报告生成方挑别的渲染路径)。
        """
        sample_block, evidence = self._build_issue_sample_block(issues)

        try:
            from openai import OpenAI
        except ImportError:
            self._log("[llm] openai 未安装,跳过 LLM 分析", color=C.YELLOW)
            return None, evidence

        labels_str = ", ".join(f"{k}({n})" for k, n in stats["top_labels"][:12])

        prompt = (
            "你是 Kubernetes 资深维护者,正在帮一个**同时运营 CaaS 平台、并在该平台上跑应用** "
            "的工程团队解读 upstream kubernetes/kubernetes 仓库的 issue 现状。\n\n"
            "请基于下面提供的数据,输出一份**三段式分析报告**(纯 markdown,不要在前后加 "
            "任何额外说明文字、不要包 ``` 代码块)。\n\n"
            "------ 数据 ------\n"
            f"过滤条件: state={self.cfg.state} since={self.cfg.since or '-'} "
            f"labels={self.cfg.labels or '-'}\n"
            f"样本数: {len(evidence)} / 总抓取数: {stats['total']}\n"
            f"状态分布: {stats['by_state']}\n"
            f"热门 label: {labels_str}\n"
            f"近期活跃度: {stats['activity_buckets']}\n\n"
            "------ Issue 样本(按 updated_at 倒序)------\n"
            f"{sample_block}\n\n"
            "------ 输出要求 ------\n\n"
            "### 1. Issue 总览(Themes)\n"
            "用 4-6 句中文,概括当前 issue 池里的**主要主题、热点 area/sig、严重度趋势**。"
            "可以指出哪些 label/区域反复出现、是否有共性根因。不要逐条复述。\n\n"
            "### 2. 对应用团队的影响(Impact on Applications)\n"
            "站在**部署应用到 K8s 的开发者**视角,挑出会直接影响以下方面的 issue:\n"
            "- 工作负载稳定性(Pod / Deployment / StatefulSet / Job)\n"
            "- 网络(Service / Ingress / NetworkPolicy / CoreDNS)\n"
            "- 存储(PV / PVC / CSI)\n"
            "- 应用层 API 兼容性 / Webhook / CRD\n"
            "聚焦最值得关注的 **5-8 条**,每条用以下格式:\n"
            "`- **#NNNNN** <一句话影响描述>。**风险**:<低/中/高> — <一句话理由>。`\n\n"
            "### 3. 对 CaaS / 平台团队的影响(Impact on CaaS Providers)\n"
            "站在**给其他团队提供 K8s as a Service 的平台运营方**视角,挑出会影响以下方面的 "
            "issue:\n"
            "- 控制面稳定性(api-server / etcd / scheduler / controller-manager)\n"
            "- 节点生命周期 / kubelet / 容器运行时\n"
            "- 集群升级 / 多租户隔离\n"
            "- 安全(RBAC / 准入控制 / supply chain)\n"
            "- 可观测性 / 资源调度公平性\n"
            "- 大规模性能 / 扩展性\n"
            "聚焦最值得关注的 **5-8 条**,同样用 `- **#NNNNN** ... **风险**: ...` 格式。\n\n"
            "------ 硬性约束 ------\n"
            "- 只能引用**样本中真实存在**的 issue 编号,严禁编造。\n"
            "- 同一个 #N 不要在第 2、3 节里都出现;选最契合的那一节。\n"
            "- 不要新增第 4 节(行动建议、总结等),只输出上面 3 个 H3 section。\n"
            "- 全程中文。\n"
        )

        try:
            client = OpenAI()
            resp = client.chat.completions.create(
                model=self.cfg.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.15,
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                self._log("[llm] 模型返回空,跳过", color=C.YELLOW)
                return None, evidence
            self._log(f"[llm] 分析完成,~{len(content)} 字符", color=C.GREEN)
            return content, evidence
        except Exception as exc:  # noqa: BLE001 — 失败时优雅降级
            self._log(
                f"[llm] 调用失败,跳过分析: {type(exc).__name__}: {exc}",
                color=C.YELLOW,
            )
            return None, evidence

    # ---------- 报告 ----------

    def _write_report(
        self,
        issues: list[dict],
        stats: dict,
        llm_analysis: str | None,
        evidence: list[dict],
        elapsed_fetch: float,
    ) -> Path:
        path = self.cfg.out_dir / f"k8s-issues-{_stamp()}.md"
        now_iso = datetime.now().isoformat(timespec="seconds")

        L: list[str] = []
        L.append("# Kubernetes Issues Report")
        L.append("")
        L.append(f"- **Generated**: {now_iso}")
        L.append(
            f"- **Repository**: [{self.cfg.repo}](https://github.com/{self.cfg.repo})"
        )
        L.append(f"- **State filter**: `{self.cfg.state}`")
        if self.cfg.since:
            L.append(f"- **Since**: `{self.cfg.since}`")
        if self.cfg.labels:
            L.append(f"- **Labels**: `{', '.join(self.cfg.labels)}`")
        L.append(f"- **Total fetched**: {stats['total']}")
        L.append(f"- **Fetch latency**: {elapsed_fetch:.2f}s")
        L.append(
            f"- **Proxy**: {'explicit ' + self.cfg.proxy if self.cfg.proxy else 'env / direct'}"
        )
        L.append(
            f"- **GitHub token**: {'yes' if self.cfg.github_token else 'no (unauth, 60 req/h)'}"
        )
        L.append(
            f"- **Analysis mode**: "
            f"{'LLM (themes + app + caas)' if self.cfg.use_llm else 'list-only (no LLM)'}"
        )
        L.append("")

        # ---- Stats(无论是否走 LLM 都先放,提供 context)----
        L.append("## Stats")
        L.append("")
        L.append("### By state")
        L.append("")
        L.append("| State | Count |")
        L.append("|---|---:|")
        for k, v in sorted(stats["by_state"].items()):
            L.append(f"| {k} | {v} |")
        L.append("")

        L.append("### By recent activity (`updated_at`)")
        L.append("")
        L.append("| Window | Count |")
        L.append("|---|---:|")
        for k in ["<=24h", "<=7d", "<=30d", "older", "unknown"]:
            if k in stats["activity_buckets"]:
                L.append(f"| {k} | {stats['activity_buckets'][k]} |")
        L.append("")

        if stats["top_labels"]:
            L.append("### Top labels")
            L.append("")
            L.append("| Label | Count |")
            L.append("|---|---:|")
            for name, n in stats["top_labels"]:
                L.append(f"| `{name}` | {n} |")
            L.append("")

        # ---- 主体:LLM 三段式分析 + Evidence 索引 ----
        if llm_analysis:
            L.append("## Analysis")
            L.append("")
            L.append(
                "> 由 LLM 基于近期 issue 样本生成的 **三段式分析**:总览主题、对应用团队的影响、"
                "对 CaaS 平台团队的影响。所有 `#NNNNN` 引用均可在文末的 _Evidence_ 表中找到原链接。"
            )
            L.append("")
            L.append(llm_analysis)
            L.append("")

            # Evidence 附录:LLM 看过的 issue 元数据,便于点进去核对
            if evidence:
                L.append("## Evidence")
                L.append("")
                L.append(
                    f"> 喂给 LLM 的 {len(evidence)} 条最近活跃 issue,作为分析里 `#NNNNN` "
                    "引用的来源索引。不是完整的 issue 列表。"
                )
                L.append("")
                L.append("| # | State | Title | Labels | Updated | Link |")
                L.append("|---:|---|---|---|---|---|")
                for it in evidence:
                    num = it.get("number")
                    state = it.get("state", "")
                    title = (it.get("title") or "").replace("|", "\\|")
                    if len(title) > 110:
                        title = title[:107] + "..."
                    labels = it.get("labels") or []
                    labels_str = ", ".join(f"`{n}`" for n in labels[:4]) or "-"
                    updated = it.get("updated_at", "")
                    url = it.get("url", "")
                    L.append(
                        f"| {num} | {state} | {title} | {labels_str} | {updated} | "
                        f"[link]({url}) |"
                    )
                L.append("")
        else:
            # ---- Fallback:LLM 不可用 → 回到原 Top N 列表 ----
            if self.cfg.use_llm:
                L.append("## Analysis")
                L.append("")
                L.append(
                    "> ⚠️ 本次 LLM 调用失败或返回空,已退回到 Top-N 列表模式。"
                    "请检查 OpenAI/Ollama 配置后重试。"
                )
                L.append("")

            listed = min(self.cfg.top_n_listed, len(issues))
            L.append(f"## Top {listed} most-recently-updated issues")
            L.append("")
            L.append("| # | State | Title | Labels | Updated | Comments | Link |")
            L.append("|---:|---|---|---|---|---:|---|")
            for it in issues[:listed]:
                num = it.get("number")
                state = it.get("state")
                title = (it.get("title") or "").replace("|", "\\|").replace("\n", " ")
                if len(title) > 100:
                    title = title[:97] + "..."
                label_names = [
                    (lbl.get("name") if isinstance(lbl, dict) else str(lbl))
                    for lbl in (it.get("labels") or [])
                ]
                labels_str = ", ".join(f"`{n}`" for n in label_names[:5]) or "-"
                updated = it.get("updated_at", "")
                comments = it.get("comments", 0)
                url = it.get("html_url", "")
                L.append(
                    f"| {num} | {state} | {title} | {labels_str} | {updated} | "
                    f"{comments} | [link]({url}) |"
                )
            L.append("")

        L.append("---")
        L.append("")
        L.append(
            f"_Generated by `issues_agent.py`; "
            f"state={self.cfg.state} max_pages={self.cfg.max_pages or '∞'} "
            f"max_issues={self.cfg.max_issues or '∞'} "
            f"use_llm={self.cfg.use_llm} model={self.cfg.model}_"
        )
        L.append("")

        path.write_text("\n".join(L), encoding="utf-8")
        return path

    # ---------- 日志 ----------

    def _log(self, msg: str, *, color: str = C.DIM) -> None:
        if not self.cfg.verbose:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"{C.DIM}[{ts}]{C.RESET} {color}{msg}{C.RESET}")


# =============================================================================
# 三种触发模式
# =============================================================================


def run_once(cfg: IssuesAgentConfig) -> Path:
    """手动触发:跑一次后返回报告路径。"""
    return IssuesAgent(cfg).run()


def run_schedule(cfg: IssuesAgentConfig, interval: int) -> None:
    """定时触发:每 interval 秒跑一次,Ctrl+C 优雅退出。"""
    stop = threading.Event()

    def handler(signum, frame):
        print(f"\n{C.YELLOW}[schedule] 收到信号 {signum},优雅退出...{C.RESET}")
        stop.set()

    signal.signal(signal.SIGINT, handler)
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, handler)
        except (ValueError, OSError):
            pass  # Windows 上某些场景不支持

    print(
        f"\n{C.BOLD}{C.CYAN}[schedule]{C.RESET} 每 {interval}s 触发一次。"
        f"Ctrl+C 退出。out_dir={cfg.out_dir}"
    )

    runs = 0
    while not stop.is_set():
        runs += 1
        print(f"\n{C.BOLD}{C.BLUE}── run #{runs} ──{C.RESET}")
        try:
            run_once(cfg)
        except Exception as exc:  # noqa: BLE001 — 定时任务必须吞掉异常继续
            print(f"{C.RED}[schedule] run #{runs} 失败: {type(exc).__name__}: {exc}{C.RESET}")
        # 用 Event.wait 而不是 sleep,这样信号可以立即打断
        stop.wait(interval)

    print(f"{C.DIM}[schedule] 已退出。共执行 {runs} 次。{C.RESET}")


def run_serve(cfg: IssuesAgentConfig, host: str, port: int, token: str | None) -> None:
    """指令触发 + 浏览器 UI:`GET /` 查看与触发,`POST /api/trigger` 远程触发。

    /api/trigger 是 **fire-and-forget**:把 IssuesAgent.run 扔到后台线程,
    HTTP 立刻返回 202;UI 通过轮询 /api/status 判断是否跑完。
    """
    try:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
        from starlette.routing import Route
    except ImportError:
        print(
            f"{C.RED}serve 模式需要 starlette + uvicorn"
            f"(本仓库 requirements 已经间接装过 mcp,自带这两个包){C.RESET}"
        )
        sys.exit(1)

    # ---------- 服务级共享状态 ----------
    state_lock = threading.Lock()
    state: dict = {
        "busy": False,
        "current_job": None,  # {"started_at": iso, "params": {...}}
        "last_run": {
            "path": None,
            "ts": None,
            "duration_s": None,
            "error": None,
            "params": None,
        },
    }

    def _base_cfg_dict() -> dict:
        return {
            "repo": cfg.repo,
            "state": cfg.state,
            "since": cfg.since,
            "labels": cfg.labels,
            "max_pages": cfg.max_pages,
            "max_issues": cfg.max_issues,
            "per_page": cfg.per_page,
            "top_n_listed": cfg.top_n_listed,
            "use_llm": cfg.use_llm,
            "out_dir": str(cfg.out_dir),
            "has_proxy": bool(cfg.proxy),
            "has_github_token": bool(cfg.github_token),
        }

    def _merge_overrides(body: dict) -> tuple[IssuesAgentConfig, dict]:
        """把 UI 传来的覆盖参数合并到 base cfg,返回新 cfg + 实际生效参数字典。"""
        params: dict = {}

        def pick(key, default):
            if key in body and body[key] is not None and body[key] != "":
                params[key] = body[key]
                return body[key]
            return default

        state_val = pick("state", cfg.state)
        if state_val not in ("open", "closed", "all"):
            state_val = cfg.state

        labels_val = body.get("labels", cfg.labels)
        if isinstance(labels_val, str):
            labels_val = [s.strip() for s in labels_val.split(",") if s.strip()]
        elif not isinstance(labels_val, list):
            labels_val = cfg.labels
        if labels_val and labels_val != cfg.labels:
            params["labels"] = labels_val

        merged = IssuesAgentConfig(
            repo=pick("repo", cfg.repo),
            state=state_val,
            since=pick("since", cfg.since) or None,
            labels=labels_val,
            max_pages=int(pick("max_pages", cfg.max_pages)),
            max_issues=int(pick("max_issues", cfg.max_issues)),
            per_page=cfg.per_page,
            proxy=cfg.proxy,
            github_token=cfg.github_token,
            timeout_s=cfg.timeout_s,
            out_dir=cfg.out_dir,
            use_llm=bool(pick("use_llm", cfg.use_llm)),
            model=cfg.model,
            top_n_listed=int(pick("top_n_listed", cfg.top_n_listed)),
            verbose=cfg.verbose,
        )
        return merged, params

    def _run_in_background(merged_cfg: IssuesAgentConfig, params: dict) -> None:
        t0 = time.perf_counter()
        error: str | None = None
        report_path: Path | None = None
        try:
            report_path = run_once(merged_cfg)
        except Exception as exc:  # noqa: BLE001 — 后台任务,捕获所有异常上抛到 UI
            error = f"{type(exc).__name__}: {exc}"
            print(f"{C.RED}[serve] 后台抓取失败: {error}{C.RESET}")

        with state_lock:
            state["busy"] = False
            state["current_job"] = None
            state["last_run"] = {
                "path": str(report_path) if report_path else None,
                "name": report_path.name if report_path else None,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "duration_s": round(time.perf_counter() - t0, 2),
                "error": error,
                "params": params,
            }

    # ---------- 路由处理器 ----------

    async def health(request: Request):
        return PlainTextResponse("ok")

    async def index(request: Request):
        return HTMLResponse(INDEX_HTML)

    async def get_status(request: Request):
        with state_lock:
            return JSONResponse(
                {
                    "base_config": _base_cfg_dict(),
                    "busy": state["busy"],
                    "current_job": state["current_job"],
                    "last_run": state["last_run"],
                    "token_required": bool(token),
                    "default_proxy": DEFAULT_PROXY,
                }
            )

    async def list_reports(request: Request):
        out = cfg.out_dir
        if not out.exists():
            return JSONResponse([])
        items = []
        for f in sorted(
            out.glob("k8s-issues-*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                st = f.stat()
            except OSError:
                continue
            items.append(
                {
                    "name": f.name,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                }
            )
        return JSONResponse(items)

    async def get_report(request: Request):
        name = request.path_params.get("name", "")
        # 路径穿越保护
        if (
            not name
            or any(ch in name for ch in ("/", "\\"))
            or ".." in name
            or not name.endswith(".md")
        ):
            return PlainTextResponse("invalid name", status_code=400)
        p = cfg.out_dir / name
        try:
            p_resolved = p.resolve()
            p_resolved.relative_to(cfg.out_dir.resolve())
        except (ValueError, OSError):
            return PlainTextResponse("invalid path", status_code=400)
        if not p_resolved.exists() or not p_resolved.is_file():
            return PlainTextResponse("not found", status_code=404)
        try:
            text = p_resolved.read_text(encoding="utf-8")
        except OSError as exc:
            return PlainTextResponse(f"read error: {exc}", status_code=500)
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")

    async def post_trigger(request: Request):
        # Token 鉴权
        if token:
            given = request.headers.get("X-Trigger-Token") or request.query_params.get(
                "token"
            )
            if given != token:
                return JSONResponse({"error": "unauthorized"}, status_code=401)

        try:
            body = await request.json()
            if not isinstance(body, dict):
                body = {}
        except Exception:  # noqa: BLE001 — 空 body / 非 JSON 都接受为 {}
            body = {}

        with state_lock:
            if state["busy"]:
                return JSONResponse(
                    {
                        "status": "busy",
                        "current_job": state["current_job"],
                    },
                    status_code=409,
                )
            merged_cfg, params = _merge_overrides(body)
            job = {
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "params": params,
            }
            state["busy"] = True
            state["current_job"] = job

        threading.Thread(
            target=_run_in_background,
            args=(merged_cfg, params),
            daemon=True,
            name="issues-agent-trigger",
        ).start()

        return JSONResponse({"status": "started", "job": job}, status_code=202)

    app = Starlette(
        routes=[
            Route("/", index),
            Route("/health", health),
            Route("/api/status", get_status),
            Route("/api/reports", list_reports),
            Route("/api/reports/{name}", get_report),
            Route("/api/trigger", post_trigger, methods=["POST"]),
            # 兼容旧 docstring 的 /trigger 路径
            Route("/trigger", post_trigger, methods=["POST"]),
        ]
    )

    print(
        f"\n{C.BOLD}{C.CYAN}[serve]{C.RESET} Issues Agent Web UI\n"
        f"  Browser : http://{host}:{port}/\n"
        f"  Trigger : POST http://{host}:{port}/api/trigger"
        f"{'  (需要 header X-Trigger-Token)' if token else ''}\n"
        f"  Status  : GET  http://{host}:{port}/api/status\n"
        f"  Reports : {cfg.out_dir.resolve()}\n"
    )
    uvicorn.run(app, host=host, port=port, log_level="warning")


# =============================================================================
# CLI
# =============================================================================


def _build_config(args: argparse.Namespace) -> IssuesAgentConfig:
    proxy = args.proxy or os.getenv("ISSUES_PROXY") or os.getenv("HTTPS_PROXY")
    if args.proxy_default and not proxy:
        proxy = DEFAULT_PROXY
    return IssuesAgentConfig(
        repo=args.repo,
        state=args.state,
        since=args.since,
        labels=[s.strip() for s in args.labels.split(",")] if args.labels else [],
        max_pages=args.max_pages,
        max_issues=args.max_issues,
        per_page=args.per_page,
        proxy=proxy,
        github_token=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"),
        out_dir=Path(args.out_dir),
        # use_llm 默认 True;--no-llm 才显式关掉
        use_llm=not args.no_llm,
        top_n_listed=args.top,
    )


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=REPO, help=f"默认 {REPO}")
    parser.add_argument(
        "--state", choices=["open", "closed", "all"], default="open"
    )
    parser.add_argument(
        "--since",
        default=None,
        help="ISO-8601 时间戳,例如 2026-04-01T00:00:00Z",
    )
    parser.add_argument(
        "--labels", default="", help="逗号分隔的 label 名;只返回带这些 label 的 issue"
    )
    parser.add_argument("--max-pages", type=int, default=0, help="0 = 不限")
    parser.add_argument("--max-issues", type=int, default=0, help="0 = 不限")
    parser.add_argument("--per-page", type=int, default=100, help="GitHub 上限 100")
    parser.add_argument("--out-dir", default="reports")
    parser.add_argument(
        "--top", type=int, default=50, help="报告里逐条详细列出的 issue 数"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="跳过 LLM 分析,改为列出 Top-N issue 表(纯客观统计,无主观解读)",
    )
    # 兼容旧示例;现在是 no-op,LLM 默认就开
    parser.add_argument("--use-llm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--proxy", default=None, help="显式代理 URL,覆盖环境变量")
    parser.add_argument(
        "--proxy-default",
        action="store_true",
        help=(
            f"当 --proxy 与 HTTPS_PROXY 都未设时,落到内置默认 {DEFAULT_PROXY}"
        ),
    )


# =============================================================================
# 浏览器 UI(内嵌单页 HTML;trigger 面板 + 报告列表 + markdown viewer)
# =============================================================================


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>K8s Issues Agent</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
  :root {
    --bg: #0d1117;
    --bg-elev: #161b22;
    --bg-elev2: #1c2128;
    --border: #30363d;
    --border-strong: #484f58;
    --fg: #c9d1d9;
    --fg-muted: #8b949e;
    --accent: #58a6ff;
    --green: #56d364;
    --orange: #f0883e;
    --purple: #d2a8ff;
    --yellow: #e3b341;
    --red: #f85149;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 'Microsoft YaHei', Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }
  .header {
    padding: 12px 22px;
    background: var(--bg-elev);
    border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
    gap: 16px; flex-wrap: wrap;
  }
  .header h1 { margin: 0; font-size: 16px; font-weight: 600; }
  .header h1 .sub { color: var(--fg-muted); font-weight: 400; margin-left: 8px; }
  .header .actions { display: flex; gap: 12px; align-items: center;
                     font-size: 13px; color: var(--fg-muted); }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; font-weight: 600; border: 1px solid var(--border);
  }
  .badge.busy   { background: rgba(240,136,62,.18);  color: var(--orange); border-color: rgba(240,136,62,.4); }
  .badge.idle   { background: rgba(86,211,100,.15);  color: var(--green);  border-color: rgba(86,211,100,.4); }
  .badge.error  { background: rgba(248,81,73,.15);   color: var(--red);    border-color: rgba(248,81,73,.4); }

  .container { display: grid; grid-template-columns: 340px 1fr; min-height: calc(100vh - 53px); }
  .left  { background: var(--bg-elev); border-right: 1px solid var(--border);
           overflow-y: auto; display: flex; flex-direction: column; }
  .right { overflow: auto; }

  .panel {
    background: var(--bg-elev2);
    border-bottom: 1px solid var(--border);
    padding: 14px 16px;
  }
  .panel h2 { margin: 0 0 10px; font-size: 13px; font-weight: 600;
              color: var(--fg-muted); text-transform: uppercase; letter-spacing: .04em; }
  .field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
  .field label { font-size: 12px; color: var(--fg-muted); }
  .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .field input[type=text], .field input[type=number], .field select {
    background: var(--bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 6px;
    padding: 6px 8px; font-size: 13px; font-family: inherit;
  }
  .field input:focus, .field select:focus { outline: 1px solid var(--accent); }
  .field-inline { display: flex; align-items: center; gap: 6px; font-size: 13px; margin-bottom: 8px; }
  .button {
    background: var(--accent); color: #fff; border: none; border-radius: 6px;
    padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
    width: 100%;
  }
  .button:hover { background: #4a8de0; }
  .button:disabled { background: var(--border-strong); cursor: not-allowed; }
  .button.secondary { background: var(--bg-elev2); color: var(--fg);
                      border: 1px solid var(--border); }
  .button.secondary:hover { background: var(--border); }

  .status-line { font-size: 12px; color: var(--fg-muted); margin-top: 8px; word-break: break-all; }
  .status-line code { background: var(--bg); padding: 1px 5px; border-radius: 4px; font-size: 11px; }
  .status-line .err { color: var(--red); }

  .reports-list { flex: 1 1 auto; overflow-y: auto; padding: 4px 0; }
  .report-item {
    padding: 9px 16px; cursor: pointer;
    border-left: 3px solid transparent;
    border-bottom: 1px solid var(--border);
    font-size: 13px; word-break: break-all;
  }
  .report-item:hover { background: var(--bg-elev2); }
  .report-item.active { background: var(--bg-elev2); border-left-color: var(--accent); }
  .report-item .meta { color: var(--fg-muted); font-size: 11px; margin-top: 3px;
                       display: flex; gap: 10px; }
  .report-item .meta .new {
    color: var(--green); border: 1px solid rgba(86,211,100,.4);
    padding: 0 5px; border-radius: 8px; font-size: 10px;
  }

  .markdown-body { padding: 24px 32px; max-width: 980px; }
  .markdown-body.empty { color: var(--fg-muted); font-style: italic; }
  .markdown-body h1 { border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  .markdown-body h2 { border-bottom: 1px solid var(--border); padding-bottom: 6px; margin-top: 28px; }
  .markdown-body h3 { margin-top: 20px; }
  .markdown-body a { color: var(--accent); text-decoration: none; }
  .markdown-body a:hover { text-decoration: underline; }
  .markdown-body code { background: var(--bg-elev); padding: 1px 5px;
                        border-radius: 4px; font-size: 12.5px;
                        font-family: 'JetBrains Mono', 'Consolas', monospace; }
  .markdown-body pre { background: var(--bg-elev); padding: 12px 14px;
                       border: 1px solid var(--border); border-radius: 6px; overflow-x: auto; }
  .markdown-body pre code { background: transparent; padding: 0; font-size: 12.5px; }
  .markdown-body table { border-collapse: collapse; margin: 12px 0;
                         display: block; overflow-x: auto; }
  .markdown-body table th, .markdown-body table td {
    border: 1px solid var(--border); padding: 5px 10px; font-size: 13px;
  }
  .markdown-body table th { background: var(--bg-elev); font-weight: 600; }
  .markdown-body table tr:nth-child(even) td { background: rgba(255,255,255,.02); }
  .markdown-body blockquote {
    border-left: 3px solid var(--border-strong); margin: 12px 0;
    padding: 4px 14px; color: var(--fg-muted);
  }
  .markdown-body hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }

  .toast {
    position: fixed; right: 20px; bottom: 20px;
    background: var(--bg-elev); border: 1px solid var(--border);
    padding: 10px 14px; border-radius: 6px; font-size: 13px;
    max-width: 380px; z-index: 100;
  }
  .toast.ok    { border-color: rgba(86,211,100,.5);  color: var(--green); }
  .toast.err   { border-color: rgba(248,81,73,.5);   color: var(--red); }
  .toast.info  { border-color: rgba(88,166,255,.5);  color: var(--accent); }

  .spin {
    display: inline-block; width: 11px; height: 11px;
    border: 2px solid var(--border-strong); border-top-color: var(--orange);
    border-radius: 50%; animation: spin .8s linear infinite;
    vertical-align: -2px; margin-right: 4px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
  <div class="header">
    <h1>K8s Issues Agent <span class="sub" id="repoLabel">kubernetes/kubernetes</span></h1>
    <div class="actions">
      <span id="statusBadge" class="badge idle">idle</span>
      <label><input type="checkbox" id="autoRefresh" checked /> 自动刷新 (3s)</label>
      <button class="button secondary" id="btnRefresh" style="width:auto;">刷新</button>
    </div>
  </div>

  <div class="container">
    <div class="left">
      <!-- 触发面板 -->
      <div class="panel">
        <h2>Trigger</h2>

        <div class="field">
          <label>State</label>
          <select id="fState">
            <option value="open">open</option>
            <option value="closed">closed</option>
            <option value="all">all</option>
          </select>
        </div>

        <div class="field">
          <label>Since (ISO-8601, 可空)</label>
          <input type="text" id="fSince" placeholder="2026-04-01T00:00:00Z">
        </div>

        <div class="field">
          <label>Labels (逗号分隔, 可空)</label>
          <input type="text" id="fLabels" placeholder="kind/bug, priority/critical-urgent">
        </div>

        <div class="field-row">
          <div class="field">
            <label>max_pages</label>
            <input type="number" id="fMaxPages" min="0" value="0">
          </div>
          <div class="field">
            <label>max_issues</label>
            <input type="number" id="fMaxIssues" min="0" value="0">
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label>top (列表条数)</label>
            <input type="number" id="fTop" min="1" value="50">
          </div>
          <div class="field-inline" style="align-self:end; margin-bottom: 4px;">
            <input type="checkbox" id="fUseLlm" checked>
            <label for="fUseLlm" style="font-size:13px;" title="LLM 生成三段式分析: Themes / App / CaaS。关掉则退回 Top-N 列表。">LLM analysis</label>
          </div>
        </div>

        <div class="field" id="tokenField" style="display:none;">
          <label>Trigger Token</label>
          <input type="text" id="fToken" placeholder="X-Trigger-Token">
        </div>

        <button class="button" id="btnTrigger">▶ 触发一次抓取</button>

        <div class="status-line" id="statusLine">…</div>
      </div>

      <!-- 报告列表 -->
      <div class="panel" style="padding-bottom:6px;">
        <h2>Reports</h2>
        <div class="status-line" id="reportsMeta">…</div>
      </div>
      <div class="reports-list" id="reportsList"></div>
    </div>

    <div class="right">
      <div class="markdown-body empty" id="viewer">
        <p>从左侧选择一个报告查看,或点「触发一次抓取」生成新的报告。</p>
      </div>
    </div>
  </div>

  <div id="toast" class="toast" style="display:none;"></div>

<script>
const $ = (id) => document.getElementById(id);
let CURRENT_REPORT = null;
let LAST_RUN_PATH = null;
let TOKEN_REQUIRED = false;
let REPORTS_KNOWN = new Set();   // 用于标记 "new"
let FIRST_LOAD_DONE = false;

// ----- 持久化:把表单 / token 存到 localStorage -----
// v2: 默认翻转为 use_llm=true,旧 v1 的 use_llm=false 不能覆盖新默认
const LS_KEY = "k8s-issues-agent-form-v2";
function loadForm() {
  try {
    const s = JSON.parse(localStorage.getItem(LS_KEY) || "{}");
    if (s.state)        $("fState").value = s.state;
    if (s.since)        $("fSince").value = s.since;
    if (s.labels)       $("fLabels").value = s.labels;
    if (s.max_pages !== undefined) $("fMaxPages").value = s.max_pages;
    if (s.max_issues !== undefined) $("fMaxIssues").value = s.max_issues;
    if (s.top)          $("fTop").value = s.top;
    // 只在 localStorage 显式存过 use_llm 时才覆盖默认(避免旧版用户被踢回 false)
    if (s.use_llm !== undefined) $("fUseLlm").checked = !!s.use_llm;
    if (s.token)        $("fToken").value = s.token;
  } catch {}
}
function saveForm() {
  const s = {
    state: $("fState").value,
    since: $("fSince").value.trim(),
    labels: $("fLabels").value.trim(),
    max_pages: parseInt($("fMaxPages").value) || 0,
    max_issues: parseInt($("fMaxIssues").value) || 0,
    top: parseInt($("fTop").value) || 50,
    use_llm: $("fUseLlm").checked,
    token: $("fToken").value.trim(),
  };
  localStorage.setItem(LS_KEY, JSON.stringify(s));
}

// ----- toast -----
function toast(msg, kind="info", ms=3000) {
  const el = $("toast");
  el.className = "toast " + kind;
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.style.display = "none"), ms);
}

// ----- format helpers -----
function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024*1024) return (n/1024).toFixed(1) + " KB";
  return (n/1024/1024).toFixed(1) + " MB";
}
function fmtTime(ts) {
  const d = new Date(ts*1000);
  return d.toLocaleString();
}

// ----- API -----
async function api(path, opts={}) {
  const r = await fetch(path, opts);
  return r;
}

async function refreshStatus() {
  try {
    const r = await api("/api/status");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const s = await r.json();

    if (s.base_config && s.base_config.repo) {
      $("repoLabel").textContent = s.base_config.repo;
    }
    TOKEN_REQUIRED = !!s.token_required;
    $("tokenField").style.display = TOKEN_REQUIRED ? "flex" : "none";

    const badge = $("statusBadge");
    if (s.busy) {
      badge.className = "badge busy";
      badge.innerHTML = '<span class="spin"></span>running';
      $("btnTrigger").disabled = true;
    } else {
      $("btnTrigger").disabled = false;
      if (s.last_run && s.last_run.error) {
        badge.className = "badge error";
        badge.textContent = "error";
      } else if (s.last_run && s.last_run.ts) {
        badge.className = "badge idle";
        badge.textContent = "idle";
      } else {
        badge.className = "badge idle";
        badge.textContent = "idle";
      }
    }

    // 状态行
    const parts = [];
    if (s.busy && s.current_job) {
      parts.push(`<span class="spin"></span>job @ ${s.current_job.started_at}`);
      const p = s.current_job.params || {};
      if (Object.keys(p).length) parts.push(`override: <code>${JSON.stringify(p)}</code>`);
    } else if (s.last_run && s.last_run.ts) {
      const lr = s.last_run;
      if (lr.error) {
        parts.push(`<span class="err">FAIL @ ${lr.ts}: ${lr.error}</span>`);
      } else {
        parts.push(`✓ last run @ ${lr.ts} (${lr.duration_s}s)`);
        if (lr.name) parts.push(`→ <code>${lr.name}</code>`);
      }
      LAST_RUN_PATH = lr.name || null;
    } else {
      parts.push("尚未触发过。");
    }
    if (s.base_config) {
      const bc = s.base_config;
      parts.push(`<br/>defaults: state=<code>${bc.state}</code> max_pages=${bc.max_pages||"∞"} max_issues=${bc.max_issues||"∞"} use_llm=${bc.use_llm} proxy=${bc.has_proxy?"yes":"env"} gh_token=${bc.has_github_token?"yes":"no"}`);
    }
    $("statusLine").innerHTML = parts.join(" ");

    return s;
  } catch (exc) {
    $("statusBadge").className = "badge error";
    $("statusBadge").textContent = "no server";
    $("statusLine").innerHTML = `<span class="err">无法连接 /api/status: ${exc.message}</span>`;
    return null;
  }
}

async function refreshReports() {
  try {
    const r = await api("/api/reports");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const items = await r.json();
    $("reportsMeta").textContent = items.length + " 份报告";

    const list = $("reportsList");
    list.innerHTML = "";
    for (const it of items) {
      const isNew = FIRST_LOAD_DONE && !REPORTS_KNOWN.has(it.name);
      const div = document.createElement("div");
      div.className = "report-item" + (it.name === CURRENT_REPORT ? " active" : "");
      div.dataset.name = it.name;
      div.innerHTML = `
        <div>${it.name}</div>
        <div class="meta">
          <span>${fmtBytes(it.size)}</span>
          <span>${fmtTime(it.mtime)}</span>
          ${isNew ? '<span class="new">NEW</span>' : ""}
        </div>`;
      div.onclick = () => loadReport(it.name);
      list.appendChild(div);
    }
    // 更新已知集合
    const known = new Set(items.map(it => it.name));
    if (!FIRST_LOAD_DONE) {
      REPORTS_KNOWN = known;
      FIRST_LOAD_DONE = true;
    } else {
      for (const n of known) REPORTS_KNOWN.add(n);
    }
    return items;
  } catch (exc) {
    $("reportsMeta").innerHTML = `<span class="err">列表加载失败: ${exc.message}</span>`;
    return [];
  }
}

async function loadReport(name) {
  CURRENT_REPORT = name;
  // 标记 active
  document.querySelectorAll(".report-item").forEach(el => {
    el.classList.toggle("active", el.dataset.name === name);
  });
  // 记录到 URL hash 方便分享
  history.replaceState(null, "", "#" + encodeURIComponent(name));

  const viewer = $("viewer");
  viewer.className = "markdown-body";
  viewer.innerHTML = '<p style="color:var(--fg-muted)">加载中…</p>';
  try {
    const r = await api("/api/reports/" + encodeURIComponent(name));
    if (!r.ok) throw new Error("HTTP " + r.status);
    const text = await r.text();
    if (typeof marked !== "undefined") {
      viewer.innerHTML = marked.parse(text, { mangle: false, headerIds: false });
    } else {
      // marked 没加载成功 → 回退到 <pre>
      const pre = document.createElement("pre");
      pre.textContent = text;
      viewer.innerHTML = "";
      viewer.appendChild(pre);
    }
  } catch (exc) {
    viewer.innerHTML = `<p style="color:var(--red)">加载失败: ${exc.message}</p>`;
  }
}

async function trigger() {
  saveForm();
  const body = {
    state: $("fState").value,
    since: $("fSince").value.trim() || null,
    labels: $("fLabels").value.trim(),
    max_pages: parseInt($("fMaxPages").value) || 0,
    max_issues: parseInt($("fMaxIssues").value) || 0,
    top_n_listed: parseInt($("fTop").value) || 50,
    use_llm: $("fUseLlm").checked,
  };
  const headers = { "Content-Type": "application/json" };
  if (TOKEN_REQUIRED) {
    const tk = $("fToken").value.trim();
    if (!tk) { toast("需要 Trigger Token", "err"); return; }
    headers["X-Trigger-Token"] = tk;
  }
  $("btnTrigger").disabled = true;
  try {
    const r = await fetch("/api/trigger", {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (r.status === 401) { toast("token 不正确", "err"); return; }
    if (r.status === 409) { toast("已经有任务在跑,请稍候", "err"); return; }
    if (!r.ok) {
      const t = await r.text();
      toast("触发失败: " + t.slice(0,200), "err"); return;
    }
    toast("已触发,后台抓取中…", "ok");
    refreshStatus();
  } catch (exc) {
    toast("网络错误: " + exc.message, "err");
  } finally {
    setTimeout(() => refreshStatus(), 500);
  }
}

let _lastLastRunPath = null;
async function tick() {
  const s = await refreshStatus();
  await refreshReports();
  // 如果刚跑完一次新报告,自动加载它
  if (s && s.last_run && s.last_run.name &&
      s.last_run.name !== _lastLastRunPath && !s.busy) {
    _lastLastRunPath = s.last_run.name;
    if (FIRST_LOAD_DONE) {
      loadReport(s.last_run.name);
      toast("新报告生成: " + s.last_run.name, "ok", 4000);
    }
  }
}

// ----- init -----
loadForm();
$("btnTrigger").onclick = trigger;
$("btnRefresh").onclick = tick;
["fState","fSince","fLabels","fMaxPages","fMaxIssues","fTop","fUseLlm","fToken"].forEach(id => {
  $(id).addEventListener("change", saveForm);
});

// 启动:加载状态 + 报告列表;若 URL hash 指定了报告,加载它
(async () => {
  await tick();
  const hash = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (hash && document.querySelector(`.report-item[data-name="${hash}"]`)) {
    loadReport(hash);
  }
})();

// 自动刷新
setInterval(() => {
  if ($("autoRefresh").checked) tick();
}, 3000);
</script>
</body>
</html>
"""


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Kubernetes Issues 收集 Agent(支持手动/定时/HTTP 指令三种触发)"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_once = sub.add_parser("once", help="手动触发:跑一次后退出")
    _add_common(p_once)

    p_sched = sub.add_parser("schedule", help="定时触发:按 interval 周期性跑")
    _add_common(p_sched)
    p_sched.add_argument(
        "--interval", type=int, default=3600, help="秒,默认 3600(1 小时)"
    )

    p_serve = sub.add_parser("serve", help="指令触发:HTTP 服务,POST /trigger")
    _add_common(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=9090)
    p_serve.add_argument(
        "--token",
        default=os.getenv("ISSUES_TRIGGER_TOKEN"),
        help="可选 token;设了之后请求需带 X-Trigger-Token header",
    )

    args = parser.parse_args()
    cfg = _build_config(args)

    if args.mode == "once":
        path = run_once(cfg)
        print(f"\n{C.BOLD}{C.GREEN}OK{C.RESET}  报告: {path}")
    elif args.mode == "schedule":
        run_schedule(cfg, args.interval)
    elif args.mode == "serve":
        run_serve(cfg, args.host, args.port, args.token)
    else:  # 不会到,argparse required=True
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
