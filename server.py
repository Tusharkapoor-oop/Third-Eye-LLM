"""Model Context Protocol (MCP) Server: MyWebEngine.

Exposes the complete 5-tool Tavily-compatible web intelligence suite:
- web_search: Multi-query consensus, domain authority scoring, two-stage passage extraction
- extract_url: Tiered HTTP-to-Stealth extraction with atomic code/table protection
- web_map: Sitemap and BFS link graph discovery with regex path filtering
- crawl_website: Deep site ingestion with in-flight semantic passage pruning
- deep_research: Autonomous multi-hop research agent with cited synthesis
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Literal

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from config import CONFIG
from crawl_engine import CrawlEngine
from extractor import TieredExtractor
from research_engine import DeepResearchEngine
from schemas import SourceItem, FailedItem
from search_pipeline import SearchPipeline


# Initialize Singletons
extractor = TieredExtractor()
search_pipeline = SearchPipeline(extractor=extractor)
research_engine = DeepResearchEngine(search_pipeline=search_pipeline)
crawl_engine = CrawlEngine(extractor=extractor)

mcp = MCPServer(
    name=CONFIG.server_name,
    version=CONFIG.server_version,
    instructions=(
        "Production-grade Web Intelligence Server providing Tavily-compatible search, "
        "tiered extraction with atomic table/code protection, site mapping, crawling, "
        "and autonomous multi-hop deep research."
    ),
)


@mcp.tool(
    name="web_search",
    description=(
        "Search the web with multi-query consensus, domain authority scoring, "
        "two-stage passage extraction, and automatic hybrid fallback."
    ),
)
async def web_search(
    query: str,
    search_depth: Literal["ultra-fast", "fast", "basic", "advanced"] = "basic",
    topic: Literal["general", "news", "finance", "coding"] = "general",
    max_results: int = 5,
    chunks_per_source: int = 3,
    time_range: Literal["day", "week", "month", "year"] | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> str:
    """Execute high-precision web search returning unified source items."""
    res = await search_pipeline.search(
        query=query,
        search_depth=search_depth,
        topic=topic,
        max_results=max_results,
        chunks_per_source=chunks_per_source,
        time_range=time_range,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="extract_url",
    description=(
        "Extract structured content and ranked passages from a URL with "
        "atomic <pre>/<code> and <table> protection and WAF fallback."
    ),
)
async def extract_url(
    url: str,
    query: str | None = None,
    chunks_per_source: int = 3,
    extract_depth: Literal["basic", "advanced"] = "basic",
) -> str:
    """Extract clean Markdown passages from target URL."""
    res = await extractor.extract_url(
        url=url,
        query=query,
        chunks_per_source=chunks_per_source,
        force_tier2=(extract_depth == "advanced"),
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="web_map",
    description=(
        "Map a website's internal URL graph using sitemap detection and "
        "BFS link discovery with regex path filtering."
    ),
)
async def web_map(
    url: str,
    max_depth: int = 2,
    max_breadth: int = 20,
    limit: int = 50,
    select_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> str:
    """Discover URLs across a target domain."""
    res = await crawl_engine.map_website(
        base_url=url,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
        select_paths=select_paths,
        exclude_paths=exclude_paths,
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="crawl_website",
    description=(
        "Crawl multiple pages across a site with in-flight semantic passage pruning "
        "and atomic code/table preservation."
    ),
)
async def crawl_website(
    url: str,
    max_depth: int = 2,
    max_breadth: int = 20,
    limit: int = 15,
    select_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    instructions: str | None = None,
    chunks_per_source: int = 3,
    extract_depth: Literal["basic", "advanced"] = "basic",
) -> str:
    """Crawl and extract passages across a website."""
    res = await crawl_engine.crawl_website(
        base_url=url,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
        select_paths=select_paths,
        exclude_paths=exclude_paths,
        instructions=instructions,
        chunks_per_source=chunks_per_source,
        extract_depth=extract_depth,
    )
    return res.model_dump_json(indent=2)


@mcp.tool(
    name="deep_research",
    description=(
        "Execute autonomous multi-hop research with query planning, "
        "gap analysis, and cited Markdown synthesis."
    ),
)
async def deep_research(
    input_prompt: str,
    mode: Literal["mini", "pro"] = "mini",
) -> str:
    """Execute autonomous deep research pipeline."""
    res = await research_engine.conduct_research(
        prompt=input_prompt,
        mode=mode,
    )
    return res.model_dump_json(indent=2)


async def run_server() -> None:
    """Run MCP server over STDIO or Streamable HTTP."""
    parser = argparse.ArgumentParser(description="MyWebEngine MCP Server")
    parser.add_argument("--http", action="store_true", help="Run Streamable HTTP transport instead of STDIO")
    parser.add_argument("--host", default=CONFIG.host, help="Bind host for HTTP transport")
    parser.add_argument("--port", type=int, default=CONFIG.port, help="Bind port for HTTP transport")
    args = parser.parse_args()

    try:
        if args.http:
            print(f"Starting {CONFIG.server_name} on http://{args.host}:{args.port}/mcp ...", file=sys.stderr)
            import uvicorn
            app = mcp.streamable_http_app()
            config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()
        else:
            await mcp.run_stdio_async()
    finally:
        await extractor.close()


def main() -> None:
    """Entry point for CLI script."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()

