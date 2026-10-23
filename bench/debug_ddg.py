import asyncio
import sys
from urllib.parse import quote_plus

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lxml import html as lxml_html

from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    url = "https://lite.duckduckgo.com/lite/?q=" + quote_plus("trafilatura python boilerplate extraction")
    r = await f.fetch(url, headers={"Accept": "text/html"}, cache_ttl=0)
    doc = lxml_html.fromstring(r.text)
    for a in doc.cssselect("a.result-link")[:5]:
        print("HREF", (a.get("href") or "")[:180])
        print("TXT ", " ".join(a.text_content().split())[:80])
    print("result-link", len(doc.cssselect("a.result-link")))
    print("result-snippet", len(doc.cssselect(".result-snippet")))
    print("links", len(doc.cssselect("a")))
    for a in doc.cssselect("a")[:12]:
        print("A", (a.get("href") or "")[:80], "|", " ".join(a.text_content().split())[:50])
    await f.close()


asyncio.run(main())
