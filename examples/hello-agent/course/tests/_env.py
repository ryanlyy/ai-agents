"""课程测试共享配置——读 examples/hello-agent/.env, 把 ollama 当 OpenAI 兼容端点用.

repo 目录结构:
    <repo>/course/tests/_env.py                ← 本文件
    <repo>/examples/hello-agent/.env           ← 目标 env 文件
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

# Windows GBK stdout 不支持 emoji——强制 utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / "examples" / "hello-agent" / ".env"
load_dotenv(ENV_PATH)

# Ollama 内网直连,不走代理
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "10.67.34.44,localhost,127.0.0.1,::1"

API_KEY   = os.getenv("OPENAI_API_KEY", "ollama")
BASE_URL  = os.getenv("OPENAI_BASE_URL", "http://10.67.34.44:11434/v1")
MODEL     = os.getenv("AGENT_MODEL", os.getenv("LLM_MODEL", "gpt-oss:20b"))
EMB_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")
EMB_HOST  = os.getenv("EMBED_BASE_URL", "http://10.67.34.44:11434")

def banner(name: str):
    print(f"\n{'='*70}\n[TEST] {name}\n  model={MODEL}  base={BASE_URL}\n{'='*70}")

def ok(msg: str):
    print(f"[PASS] {msg}")

def fail(msg: str):
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)
