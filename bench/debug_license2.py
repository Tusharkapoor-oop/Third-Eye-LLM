import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher
from weblens.extract import ExtractionService
async def main():
    s=Settings(); c=Cache(s); f=SafeFetcher(s,c); ex=ExtractionService(s,f,c)
    doc=await ex.fetch_doc("https://github.com/adbar/trafilatura/blob/master/LICENSE", allow_browser=False)
    t=doc.text; low=t.lower()
    i=low.find("apache")
    print("len",len(t),"idx",i)
    print(repr(t[max(0,i-300):i+500]))
    print("contains pre fence", "```" in t)
    await ex.close(); await f.close()
asyncio.run(main())
