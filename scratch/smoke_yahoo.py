import asyncio

from weblens.config import Settings
from weblens.service import WebLens


async def main() -> None:
    settings = Settings(
        search_providers="yahoo",
        cache_enabled=False,
        allow_browser=False,
        provider_timeout_s=6.0,
    )
    service = WebLens(settings)
    result = await service.search("python asyncio gather", max_results=3, max_tokens=400)
    print(result.get("status"), result.get("fail"), result.get("warn"))
    for hit in result.get("res", []):
        print(hit.get("u"), "|", hit.get("t"))


asyncio.run(main())
