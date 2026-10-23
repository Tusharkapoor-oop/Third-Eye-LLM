import asyncio
import re
import sys
from urllib.parse import quote_plus

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lxml import html as lxml_html

from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher

QUERY = "trafilatura python boilerplate extraction"


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    q = quote_plus(QUERY)
    for name, url in [
        ("ddg-lite", f"https://lite.duckduckgo.com/lite/?q={q}"),
        ("google", f"https://www.google.com/search?q={q}&num=10&hl=en"),
    ]:
        try:
            r = await f.fetch(url, headers={"Accept": "text/html"}, cache_ttl=0, max_bytes=2_000_000)
        except Exception as e:
            print(name, "FAIL", e)
            continue
        t = r.text
        print("\n==", name, r.status, len(t))
        text = re.sub(r"<script.*?</script>", " ", t, flags=re.S)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        print("TEXT:", text[:1500])
        doc = lxml_html.fromstring(t)
        links = [(a.get("href", ""), " ".join(a.text_content().split())) for a in doc.iter("a")]
        print("links", len(links))
        for href, txt in links[:25]:
            if href.startswith("http"):
                print("  ", txt[:60], "|", href[:100])
    await f.close()


asyncio.run(main())
