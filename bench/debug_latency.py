import asyncio
import sys
import time
from urllib.parse import quote_plus

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher


async def main() -> None:
    s = Settings()
    s.cache_enabled = False
    c = Cache(s)
    f = SafeFetcher(s, c)
    q = quote_plus("trafilatura python boilerplate extraction")
    for name, url in [
        ("ddg-lite", f"https://lite.duckduckgo.com/lite/?q={q}&kl=us-en"),
        ("ddg-html", f"https://html.duckduckgo.com/html/?q={q}&kl=us-en"),
        ("bing", f"https://www.bing.com/search?q={q}&count=10&setlang=en&cc=us"),
    ]:
        for i in range(2):
            t0 = time.perf_counter()
            try:
                r = await f.fetch(url, headers={"Accept": "text/html"}, use_cache=False)
                ms = (time.perf_counter() - t0) * 1000
                print(f"{name} run{i} {ms:.0f}ms status={r.status} len={len(r.body)} ct={r.content_type} results={r.text.count('result-link')}")
            except Exception as e:
                print(name, "FAIL", e)
        await asyncio.sleep(1)
    await f.close()


asyncio.run(main())
