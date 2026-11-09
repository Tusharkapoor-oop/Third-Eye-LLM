"""
High-Performance Model Context Protocol (MCP) Server.
Implements the 5 core tools for live search, extraction, crawling, mapping, and deep research.
Supports both STDIO (default) and Streamable HTTP transports.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import mcp.types as t
from mcp.server.mcpserver import MCPServer

try:
    from engine.config import CONFIG
    from engine.crawl.crawler import WebsiteCrawler
    from engine.crawl.mapper import WebsiteMapper
    from engine.extract.extractor import DocumentExtractor
    from engine.research.deep_research import DeepResearchEngine
    from engine.search.aggregator import SearchAggregator
except ImportError:  # pragma: no cover - supports running from repo root
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.config import CONFIG
    from engine.crawl.crawler import WebsiteCrawler
    from engine.crawl.mapper import WebsiteMapper
    from engine.extract.extractor import DocumentExtractor
    from engine.research.deep_research import DeepResearchEngine
    from engine.search.aggregator import SearchAggregator

# Lazy-loaded engine singletons for sub-second process startup
_aggregator: SearchAggregator | None = None
_extractor: DocumentExtractor | None = None
_crawler: WebsiteCrawler | None = None
_mapper: WebsiteMapper | None = None
_researcher: DeepResearchEngine | None = None

def get_aggregator() -> SearchAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = SearchAggregator()
    return _aggregator

def get_extractor() -> DocumentExtractor:
    global _extractor
    if _extractor is None:
        _extractor = DocumentExtractor()
    return _extractor

def get_crawler() -> WebsiteCrawler:
    global _crawler
    if _crawler is None:
        _crawler = WebsiteCrawler()
    return _crawler

def get_mapper() -> WebsiteMapper:
    global _mapper
    if _mapper is None:
        _mapper = WebsiteMapper()
    return _mapper

def get_researcher() -> DeepResearchEngine:
    global _researcher
    if _researcher is None:
        _researcher = DeepResearchEngine()
    return _researcher

def format_result(data: dict[str, Any]) -> t.CallToolResult:
    """Formats output for both legacy TextContent clients and MCP 2026 structuredContent clients."""
    compact_json = json.dumps(data, separators=(",", ":"))
    return t.CallToolResult(
        content=[t.TextContent(type="text", text=compact_json)],
        structured_content=data,
        is_error=False
    )

def format_error(msg: str) -> t.CallToolResult:
    err_dict = {"status": "error", "message": msg}
    return t.CallToolResult(
        content=[t.TextContent(type="text", text=json.dumps(err_dict))],
        structured_content=err_dict,
        is_error=True
    )

def create_server() -> MCPServer:
    server = MCPServer(
        name=CONFIG.server_name,
        version=CONFIG.server_version,
        instructions="Local-first web intelligence engine providing search, extraction, crawling, mapping, and deep research."
    )

    @server.tool(
        name="web_search",
        description="Search the live web. Returns ranked titles, URLs, and snippets within a token budget."
    )
    async def web_search(
        query: str,
        count: int = 5,
        time_filter: str | None = None,
        domains: list[str] | None = None,
        max_tokens: int = CONFIG.default_search_tokens
    ) -> t.CallToolResult:
        try:
            aggregator = get_aggregator()
            resp = await aggregator.search(
                query=query,
                count=count,
                time_filter=time_filter,
                domains=domains,
                max_tokens=max_tokens
            )
            return format_result(resp.to_dict())
        except Exception as e:
            return format_error(f"Search failed: {e}")

    @server.tool(
        name="extract_url",
        description="Extract content from a URL. By default returns query-relevant passages with exact text spans."
    )
    async def extract_url(
        url: str,
        query: str | None = None,
        mode: str = "passages",
        max_tokens: int = CONFIG.default_extract_tokens,
        render_js: bool = False
    ) -> t.CallToolResult:
        try:
            extractor = get_extractor()
            doc = await extractor.extract_url(
                url=url,
                query=query,
                mode=mode,
                max_tokens=max_tokens,
                render_js=render_js
            )
            return format_result(doc.to_dict())
        except Exception as e:
            return format_error(f"Extraction failed: {e}")

    @server.tool(
        name="crawl_website",
        description="Bounded recursive crawl of a website starting from a seed URL."
    )
    async def crawl_website(
        url: str,
        max_depth: int = 1,
        max_pages: int = 5,
        allowed_paths: list[str] | None = None,
        max_tokens_per_page: int = 800
    ) -> t.CallToolResult:
        try:
            crawler = get_crawler()
            res = await crawler.crawl(
                seed_url=url,
                max_depth=max_depth,
                max_pages=max_pages,
                allowed_paths=allowed_paths,
                max_tokens_per_page=max_tokens_per_page
            )
            return format_result(res)
        except Exception as e:
            return format_error(f"Crawl failed: {e}")

    @server.tool(
        name="web_map",
        description="Discovers domain topology and sitemap URLs without downloading full pages."
    )
    async def web_map(
        url: str,
        limit: int = 30
    ) -> t.CallToolResult:
        try:
            mapper = get_mapper()
            res = await mapper.map_domain(seed_url=url, limit=limit)
            return format_result(res)
        except Exception as e:
            return format_error(f"Map failed: {e}")

    @server.tool(
        name="deep_research",
        description="Autonomous multi-query research loop. Gathers evidence, cross-corroborates facts, and reports uncertainties."
    )
    async def deep_research(
        question: str,
        max_searches: int = 3,
        max_pages: int = 5,
        time_filter: str | None = None,
        max_tokens: int = CONFIG.default_research_tokens
    ) -> t.CallToolResult:
        try:
            researcher = get_researcher()
            report = await researcher.research(
                question=question,
                max_searches=max_searches,
                max_pages=max_pages,
                time_filter=time_filter,
                max_tokens=max_tokens
            )
            return format_result(report.to_dict())
        except Exception as e:
            return format_error(f"Deep research failed: {e}")

    return server

def main():
    parser = argparse.ArgumentParser(description="Personal Web Intelligence Engine MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio", help="Transport mode")
    parser.add_argument("--host", default=CONFIG.host, help="Host for HTTP transport")
    parser.add_argument("--port", type=int, default=CONFIG.port, help="Port for HTTP transport")
    args = parser.parse_args()

    server = create_server()

    if args.transport == "stdio":
        asyncio.run(server.run_stdio_async())
    elif args.transport == "http":
        import uvicorn
        app = server.streamable_http_app()
        uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
