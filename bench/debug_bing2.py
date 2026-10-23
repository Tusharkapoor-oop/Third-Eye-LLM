import asyncio
import sys
from urllib.parse import quote_plus

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lxml import etree, html as lxml_html

from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    url = (
        "https://www.bing.com/search?q="
        + quote_plus("python asyncio timeout")
        + "&count=10&setlang=en&cc=us&form=QBLH"
    )
    r = await f.fetch(url, headers={"Accept": "text/html"}, cache_ttl=600, max_bytes=1_500_000)
    doc = lxml_html.fromstring(r.text)
    lis = doc.cssselect("li.b_algo")
    print("lis", len(lis))
    if lis:
        frag = etree.tostring(lis[0], encoding="unicode")
        print(frag[:2500])
        print("h2a", len(lis[0].cssselect("h2 a")))
        print("all a", [(a.get("href"), a.text_content()[:40]) for a in lis[0].cssselect("a")][:5])
    await f.close()


asyncio.run(main())
