import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from weblens.cache import Cache
from weblens.config import Settings
from weblens.net import SafeFetcher
from weblens.extract import ExtractionService
from weblens.extract.passages import select_passages
from weblens.research.engine import sentence_candidates
async def main():
    s=Settings(); c=Cache(s); f=SafeFetcher(s,c); ex=ExtractionService(s,f,c)
    doc=await ex.fetch_doc("https://docs.python.org/3/library/asyncio-task.html", allow_browser=False)
    ps,cov=select_passages(doc.text,"what is asyncio.timeout in python",title=doc.title,max_passages=5,max_chars=6000)
    print("passages",len(ps),"cov",cov)
    for p in ps:
        print("P",p.start,p.end,len(p.text),p.text[:160].replace(chr(10)," "))
        for f in sentence_candidates(p,"what is asyncio.timeout in python",limit=3):
            print("   C",len(f.claim),f.claim[:180].replace(chr(10)," "))
    await ex.close(); await f.close()
asyncio.run(main())
