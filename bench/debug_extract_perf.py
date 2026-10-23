import asyncio
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import trafilatura

from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher


def run_variant(html: str, page_url: str, name: str, **kw) -> None:
    t0 = time.perf_counter()
    try:
        text = trafilatura.extract(html, url=page_url, **kw) or ""
    except Exception as e:
        print(name, "ERR", e)
        return
    ms = (time.perf_counter() - t0) * 1000
    heads = sum(1 for line in text.splitlines() if line.startswith("#"))
    print(f"{name}: {ms:.0f}ms len={len(text)} headings={heads}")


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    url = "https://docs.python.org/3/library/asyncio-task.html"
    r = await f.fetch(url, use_cache=True)
    html = r.text

    t0 = time.perf_counter()
    meta = trafilatura.extract_metadata(html, default_url=url)
    print(f"metadata extensive: {1000*(time.perf_counter()-t0):.0f}ms title={meta.title!r}")
    t0 = time.perf_counter()
    meta2 = trafilatura.extract_metadata(html, default_url=url, extensive=False)
    print(f"metadata fast: {1000*(time.perf_counter()-t0):.0f}ms title={meta2.title!r}")

    base = {

        "output_format": "markdown",
        "include_formatting": True,
        "include_tables": True,
        "include_links": False,
        "include_comments": False,
        "deduplicate": True,
    }
    run_variant(html, url, "current", **base)
    run_variant(html, url, "fast", **{**base, "fast": True})
    run_variant(html, url, "no-dedupe", **{**base, "deduplicate": False})
    run_variant(html, url, "fast-no-dedupe", **{**base, "fast": True, "deduplicate": False})
    run_variant(
        html,
        url,
        "txt-fast",
        **{**base, "output_format": "txt", "include_formatting": False, "fast": True},
    )
    run_variant(html, url, "markdown-precision", **{**base, "favor_precision": True})
    await f.close()


asyncio.run(main())
