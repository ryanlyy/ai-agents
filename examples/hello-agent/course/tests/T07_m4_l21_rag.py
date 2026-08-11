"""T07: M4 L21 RAG embedding + 向量召回

注意:课程文档示例用 OpenAI text-embedding-3-small,但我们环境是 Ollama nomic-embed-text.
nomic-embed-text 不走 OpenAI /v1/embeddings 兼容,而是 Ollama 原生 /api/embeddings.
本测试用 requests 直调 Ollama embedding API + chromadb 存取 + 5 query 命中率.
"""
from _env import banner, ok, fail, EMB_HOST
import requests, chromadb, uuid

# 故意覆盖 .env 里的 nomic-embed-text —— 它是英文优化,中文召回率会跌到 ~20%.
# 中文场景必须用多语言 / 中文优化的模型,如 bge-m3, qwen3-embedding, BAAI/bge-large-zh.
EMB_MODEL = "bge-m3:latest"

banner(f"M4 L21 — RAG embedding (Ollama {EMB_MODEL}) + chromadb 召回")

def embed(text: str) -> list[float]:
    r = requests.post(f"{EMB_HOST}/api/embeddings",
                      json={"model": EMB_MODEL, "prompt": text},
                      timeout=30)
    r.raise_for_status()
    return r.json()["embedding"]

# 1. 自检 embedding
v = embed("hello")
print(f"  embedding dim = {len(v)} (nomic-embed-text 应为 768)")
if not (256 <= len(v) <= 4096):
    fail(f"embedding 维度异常: {len(v)}")

# 2. 入库 10 条
chroma = chromadb.Client()
# chromadb 1.5+ 严格校验 collection 名:必须 3-512 字符, [a-zA-Z0-9._-], 且首尾必须是 alnum.
# 下划线开头会抛 InvalidArgumentError —— 这是从老版本升级时最常见的坑.
coll   = chroma.get_or_create_collection("t07-mem")

MEMORIES = [
    ("u1m01", "用户说他偏好深色主题"),
    ("u1m02", "用户使用 PostgreSQL 14"),
    ("u1m03", "用户的项目部署在阿里云杭州 region"),
    ("u1m04", "用户上次问我 Redis 缓存策略,我推荐了 LRU"),
    ("u1m05", "用户对 LangChain 有顾虑,担心抽象太重"),
    ("u1m06", "用户买了 RTX 4090 用于本地推理"),
    ("u1m07", "用户的团队规模 8 人"),
    ("u1m08", "用户在 2025 年 12 月升级了 PyTorch 到 2.5"),
    ("u1m09", "用户更喜欢 black 而不是 autopep8"),
    ("u1m10", "用户的产品定价是 $99/月 starter, $299/月 pro"),
]
for mid, text in MEMORIES:
    coll.upsert(ids=[mid], embeddings=[embed(text)], documents=[text])
print(f"  已入库 {len(MEMORIES)} 条")

# 3. 5 个查询 top-1 命中
QUERIES = [
    ("用户的颜色偏好是什么?",   "u1m01"),
    ("用什么数据库?",          "u1m02"),
    ("产品定价多少?",          "u1m10"),
    ("团队规模?",             "u1m07"),
    ("Python 缓存如何选?",     "u1m04"),
]
hits = 0
print(f"\n  | 查询 | 期望 | 实际 | 命中 |")
print(f"  |---|---|---|---|")
for q, expected in QUERIES:
    res = coll.query(query_embeddings=[embed(q)], n_results=3)
    actual = res["ids"][0][0] if res["ids"][0] else "<none>"
    hit_mark = "Y" if actual == expected else "n"
    if actual == expected: hits += 1
    print(f"  | {q:30} | {expected} | {actual} | {hit_mark} |")

rate = 100 * hits / len(QUERIES)
print(f"\n  Top-1 命中率: {hits}/{len(QUERIES)} = {rate:.0f}%")

# 容忍度: nomic-embed-text 中文嵌入比 OpenAI 弱一些,>= 60% 视为通过
if rate < 60:
    fail(f"召回率 {rate:.0f}% < 60%, 可能 nomic-embed-text 对中文较弱")
ok(f"chromadb + ollama embedding 端到端跑通, top-1 命中率 {rate:.0f}%")
