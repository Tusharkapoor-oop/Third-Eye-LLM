import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher
from weblens.search import SearchRouter
from weblens.extract import ExtractionService
from weblens.extract.passages import select_passages

async def main():
    s=Settings(); c=Cache(s); f=SafeFetcher(s,c)
    router=SearchRouter(s,f); ex=ExtractionService(s,f,c)
    out=await router.search("trafilatura license", k=8)
    print("hits", len(out.hits))
    scores={}
    for i,h in enumerate(out.hits):
        scores[h.url]=scores.get(h.url,0)+1/(1+i)
        print(i, h.url[:110], "|", h.title[:60])
    print("ranked")
    for h in sorted(out.hits, key=lambda h:-scores.get(h.url,0)):
        try:
            doc=await ex.fetch_doc(h.url, allow_browser=False)
        except Exception as e:
            print("FAIL", h.url[:90], type(e).__name__); continue
        ps,cov=select_passages(doc.text,"trafilatura license",title=doc.title,max_passages=3,max_chars=5000)
        print("PAGE", h.url[:100], "len",len(doc.text),"cov",cov,"apache20", "apache 2.0" in doc.text.lower(), "apache", "apache" in doc.text.lower())
        for p in ps:
            print("   P",p.start,p.end,p.text[:120].replace(chr(10)," "))
    await ex.close(); await f.close()
asyncio.run(main())
