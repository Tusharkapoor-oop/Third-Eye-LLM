"""Small local-MCP smoke check; not a published benchmark artifact."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "weblens" / "src"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "weblens-lab"))

from adapters.local_mcp_adapter.adapter import LocalMCPAdapter  # noqa: E402


async def main() -> None:
    adapter = LocalMCPAdapter()
    await adapter.start()
    try:
        print("tools", len(adapter.tools))
        for query in (
            "Which company developed the GPT-4 model released in March 2023?",
            "What was the name of the NASA mission that first landed humans on the Moon in July 1969?",
        ):
            result = await adapter.search(query, max_results=5)
            print("\nSEARCH", query)
            print("status", result.status, "raw", result.raw_status)
            print("warnings", (result.raw_response or {}).get("warn"))
            for item in result.results:
                print(item.url, "|", item.title)
        research = await adapter.research(
            "major new features in Python 3.14", max_tokens=800
        )
        print("\nRESEARCH", research.status, research.error)
        print("markdown", research.report_markdown[:300])
        print("sources", research.sources)
        extract_raw, _, _ = await adapter._call("extract_url", {"url": "https://example.com/"})
        print("\nEXTRACT RAW", extract_raw)
        research_raw, _, _ = await adapter._call(
            "deep_research", {"query": "major new features in Python 3.14", "max_tokens": 800}
        )
        print("\nRESEARCH RAW", research_raw)
        extract = await adapter.extract(["https://example.com/"])
        for item in extract.results:
            print("\nEXTRACT PARSED", item.url, len(item.markdown), item.status, item.error)
    finally:
        await adapter.close()


asyncio.run(main())
