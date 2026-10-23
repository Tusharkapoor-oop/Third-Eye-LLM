import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from weblens.cache import Cache
from weblens.config import Settings
from weblens.extract.html import extract_html
from weblens.extract.passages import build_chunks, query_terms, score_chunks, select_passages
from weblens.net import SafeFetcher


async def main() -> None:
    s = Settings()
    c = Cache(s)
    f = SafeFetcher(s, c)
    r = await f.fetch("https://github.com/adbar/trafilatura")
    doc = extract_html(r.text, "https://github.com/adbar/trafilatura")
    text = doc.text
    print("len", len(text))
    low = text.lower()
    idx = low.find("license")
    print("license idx", idx)
    print("context:", text[max(0, idx - 300) : idx + 500].replace("\n", " | "))
    print("terms", query_terms("license"))
    chunks = build_chunks(text)
    print("chunks", len(chunks))
    score_chunks(chunks, "license", doc.title)
    hits = [(c.idx, getattr(c, "_coverage", 0), getattr(c, "_score", 0), len(c.text), c.start, c.end) for c in chunks if "license" in c.tf]
    print("chunks with license", hits)
    for c in chunks:
        print("chunk", c.idx, c.start, c.end, [t for t in c.tokens if "lic" in t][:10], len(c.tokens))
    ps, cov = select_passages(text, "license", title=doc.title)
    print("passages", len(ps), "coverage", cov)
    for p in ps:
        print("  ", p.start, p.end, p.text[:120].replace("\n", " "))

    ps2, cov2 = select_passages(text, "what license is trafilatura under", title=doc.title)
    print("\nquery2 passages", len(ps2), "coverage", cov2)
    for p in ps2:
        print("  ", p.start, p.end, "license" in p.text.lower(), p.text[:120].replace("\n", " "))
    await f.close()


asyncio.run(main())
