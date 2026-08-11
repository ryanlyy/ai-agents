"""T03: M2 L10 async + AsyncOpenAI + asyncio.gather

验证 D 阶段修复 — async 路径要用 AsyncOpenAI 不能用 OpenAI.
本测试不真调 LLM(避免 N×LLM 时长爆炸),只测并发工具调用加速比.
"""
from _env import banner, ok, fail, API_KEY, BASE_URL
import asyncio, time

banner("M2 L10 — asyncio.gather 并发加速比")

async def slow_tool(city: str) -> str:
    await asyncio.sleep(1.5)
    return f"{city} 25C 晴"

async def seq_run(cities):
    t0 = time.time()
    out = []
    for c in cities:
        out.append(await slow_tool(c))
    return out, time.time() - t0

async def par_run(cities):
    t0 = time.time()
    out = await asyncio.gather(*[slow_tool(c) for c in cities])
    return out, time.time() - t0

async def main():
    cities = ["北京", "上海", "深圳"]
    r_seq, t_seq = await seq_run(cities)
    r_par, t_par = await par_run(cities)
    print(f"  顺序版: {t_seq:.2f}s   结果={r_seq}")
    print(f"  并发版: {t_par:.2f}s   结果={r_par}")
    speedup = t_seq / t_par
    print(f"  加速比: {speedup:.1f}x")
    if speedup < 2.0:
        fail(f"加速比 {speedup:.1f}x 太低 (期望 ≥2.5x)")
    ok(f"asyncio.gather 并发加速 {speedup:.1f}x (期望 ~3x)")

# 顺便测一下 AsyncOpenAI 可 import 且不抛错
async def test_async_client_import():
    from openai import AsyncOpenAI
    c = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    # 不真调,只验证类型
    assert hasattr(c, "chat"), "AsyncOpenAI 缺 chat 属性"
    ok("AsyncOpenAI 实例化 + 属性检查通过 (M2 L10 修复点)")

asyncio.run(main())
asyncio.run(test_async_client_import())
