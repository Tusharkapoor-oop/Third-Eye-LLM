import asyncio
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from weblens.cache import Cache
from weblens.config import Settings
from weblens.extract.html import extract_html
from weblens.net import SafeFetcher


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    for url in [
        "https://docs.python.org/3/library/asyncio-task.html",
        "https://trafilatura.readthedocs.io/en/latest/usage-python.html",
        "https://github.com/adbar/trafilatura",
    ]:
        for run in range(2):
            t0 = time.perf_counter()
            r = await f.fetch(url, use_cache=False)
            t1 = time.perf_counter()
            doc = extract_html(r.text, url)
            t2 = time.perf_counter()
            print(
                f"run{run} fetch={1000*(t1-t0):.0f}ms extract={1000*(t2-t1):.0f}ms "
                f"bytes={len(r.body)} text={len(doc.text)} html={len(r.text)}"
            )
    await f.close()


asyncio.run(main())
