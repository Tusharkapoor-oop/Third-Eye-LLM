"""Quick test of DDGS provider directly."""
import asyncio
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

from src.engine.search.ddgs_provider import DDGSearchProvider

async def test():
    p = DDGSearchProvider()
    print(f"Provider name: {p.name}")
    results = await p.search("capital of France", count=5)
    print(f"Results count: {len(results)}")
    for r in results:
        print(f"  {r.title[:60]}: {r.url} - {r.snippet[:80]}...")

asyncio.run(test())
