import asyncio

from weblens.config import Settings
from weblens.service import WebLens


async def main() -> None:
    settings = Settings(
        search_providers="wikipedia",
        cache_enabled=False,
        allow_browser=False,
    )
    service = WebLens(settings)
    for query in (
        "Which company developed the GPT-4 model released in March 2023?",
        "What was the name of the NASA mission that first landed humans on the Moon in July 1969?",
    ):
        result = await service.search(query, max_results=5, max_tokens=500)
        print("\n", query)
        print(result.get("status"), result.get("warn"))
        for hit in result.get("res", []):
            print(hit.get("u"), "|", hit.get("t"))


asyncio.run(main())
