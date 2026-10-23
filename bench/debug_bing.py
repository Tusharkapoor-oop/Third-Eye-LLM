import asyncio
import re
import sys
from urllib.parse import quote_plus

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
        + "&count=10&setlang=en&cc=us"
    )
    r = await f.fetch(url, headers={"Accept": "text/html"}, cache_ttl=0, max_bytes=1_500_000)
    t = r.text
    print("status", r.status, "len", len(t))
    for marker in ["b_results", "b_no", "b_algo", "challenge", "verify", "unusual", "captcha", "robot"]:
        print(marker, t.count(marker))
    text = re.sub(r"<script.*?</script>", "", t, flags=re.S)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    print(text[:1200])
    await f.close()


asyncio.run(main())
