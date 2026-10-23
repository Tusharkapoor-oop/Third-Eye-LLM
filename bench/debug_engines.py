import asyncio
import re
import sys
from urllib.parse import quote_plus, urlsplit

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lxml import html as lxml_html

from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher

QUERY = "trafilatura python boilerplate extraction"


async def try_engine(f: SafeFetcher, name: str, url: str) -> None:
    try:
        r = await f.fetch(url, headers={"Accept": "text/html"}, cache_ttl=0, max_bytes=2_000_000)
    except Exception as e:
        print(name, "FAIL", e)
        return
    t = r.text
    print("\n==", name, "status", r.status, "len", len(t))
    for marker in ["b_algo", "result__a", "snippet", "data-testid", "anomaly", "captcha", "consent"]:
        print(" ", marker, t.count(marker))
    try:
        doc = lxml_html.fromstring(t)
    except Exception as e:
        print(" parse fail", e)
        return
    seen = []
    for a in doc.iter("a"):
        href = a.get("href") or ""
        text = " ".join(a.text_content().split())
        if href.startswith("http") and len(text) > 25:
            host = urlsplit(href).hostname or ""
            if any(x in host for x in ["brave.com", "google.com", "gstatic", "bing.com"]):
                continue
            if href in [s[0] for s in seen]:
                continue
            seen.append((href, text))
        if len(seen) >= 8:
            break
    for href, text in seen:
        print("  -", text[:70], "|", href[:100])


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    q = quote_plus(QUERY)
    await try_engine(f, "brave-html", f"https://search.brave.com/search?q={q}&source=web")
    await try_engine(f, "google-html", f"https://www.google.com/search?q={q}&num=10&hl=en")
    await try_engine(f, "mojeek", f"https://www.mojeek.com/search?q={q}")
    await try_engine(f, "ddg-lite-post", f"https://lite.duckduckgo.com/lite/?q={q}")
    await f.close()


asyncio.run(main())
