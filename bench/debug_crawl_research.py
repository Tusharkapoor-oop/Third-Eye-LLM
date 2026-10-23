import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from weblens.cache import Cache
from weblens.config import Settings
from weblens.crawl import SiteCrawler
from weblens.extract import ExtractionService
from weblens.net import SafeFetcher
from weblens.research import ResearchEngine
from weblens.search import SearchRouter


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    ex = ExtractionService(s, f, c)
    router = SearchRouter(s, f)
    crawler = SiteCrawler(s, f, ex)
    research = ResearchEngine(s, router, ex)

    print("== MAP")
    m = await crawler.site_map("https://docs.python.org/3/library/asyncio-task.html", max_urls=12)
    print("status", m.status, "n", len(m.urls), "tok", m.tokens, "ms", m.elapsed_ms, "sitemap", m.sitemap_used)
    for e in m.urls[:5]:
        print("  ", e["u"][:100], "|", e["t"][:40])

    print("\n== CRAWL")
    cr = await crawler.crawl("https://docs.python.org/3/library/asyncio-task.html", max_pages=3, max_depth=1, query="timeout", max_tokens=1500)
    print("status", cr.status, "pages", len(cr.pages), "tok", cr.tokens, "ms", cr.elapsed_ms, "warn", cr.warnings)
    for p in cr.pages:
        print("  ", p.status, p.url[:90], "ps", len(p.passages), "warn", p.warnings)

    print("\n== RESEARCH")
    for q in ["what is asyncio.timeout in python", "trafilatura license"]:
        r = await research.research(q, max_tokens=2000)
        print("Q", q)
        print(" status", r.status, "n", len(r.findings), "tok", r.tokens, "ms", r.elapsed_ms, "gaps", r.gaps, "warn", r.warnings)
        for fd in r.findings[:3]:
            print("   -", fd.claim[:170].replace("\n", " "))
            print("     ", fd.url[:90], fd.span)

    await ex.close()
    await f.close()


asyncio.run(main())
