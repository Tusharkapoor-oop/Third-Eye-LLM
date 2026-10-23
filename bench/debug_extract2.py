import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from weblens.cache import Cache
from weblens.config import Settings
from weblens.extract import ExtractionService
from weblens.net import SafeFetcher


async def main() -> None:
    s = Settings()
    s.cache_enabled = False
    c = Cache(s)
    f = SafeFetcher(s, c)
    ex = ExtractionService(s, f, c)
    cases = [
        ("https://docs.python.org/3/library/asyncio-task.html", "asyncio timeout"),
        ("https://github.com/adbar/trafilatura", "license"),
        ("https://github.com/adbar/trafilatura", "what license is trafilatura under"),
        ("https://trafilatura.readthedocs.io/en/latest/usage-python.html", "extract markdown"),
    ]
    for url, q in cases:
        out = await ex.extract(url, query=q, max_tokens=1500)
        doc = await ex.fetch_doc(url)
        print("\n==", url, "| q:", q)
        print(
            "status", out.status, "ms", out.elapsed_ms, "tok", out.tokens,
            "ps", len(out.passages), "warn", out.warnings,
            "license_in_text", "license" in doc.text.lower(), "len", len(doc.text),
        )
        for p in out.passages[:3]:
            print("  [%d:%d] %s" % (p.start, p.end, (p.heading or "")[:50]))
            print("   ", p.text[:200].replace("\n", " "))
    await ex.close()
    await f.close()


asyncio.run(main())
