"""webintel MCP server. Official SDK v2 (mcp>=2.3), supports protocol revisions
2025-03-10 / 2025-06-18 / 2025-11-25 / 2026-07-28 via SDK negotiation.

Tool surface (4 tools, deliberately small; rationale in docs/adr/ADR-004):
  web_search       - keyless-first web search, token-capped compact SERP
  extract_url      - main-content extraction limited to query-relevant spans
  crawl_website    - bounded same-domain crawl or URL map
  deep_research    - bounded evidence-gathering loop (no LLM in the loop)

All results are compact JSON (short keys; legend in each tool description).
No relevance scores or confidence numbers are EVER returned (R2) - a gate in
bench/ tests enforces this schema invariant.
"""
from __future__ import annotations

import asyncio
import secrets
import sys
import threading
import time

from .config import load_config, Config
from .http_client import HttpPool
from .cache import Cache
from .limits import json_tokens
from .search.engine import SearchEngine
from .extract import extract_url as _extract_url
from .crawl import crawl_website as _crawl_website
from .research import deep_research as _deep_research

import threading

TOOL_TOKEN_BUDGET_DOC = 160  # informational


def _warm_imports():  # pragma: no cover - background only
    try:
        import trafilatura  # noqa: F401
        import lxml.html  # noqa: F401
        import tiktoken  # noqa: F401
        from .limits import _get_enc  # noqa: F401
        _get_enc()  # warm the token estimator so the first tool call doesn't pay for it
    except Exception:
        pass


def build_app() -> "tuple[MCP_APP, Config]":  # noqa: F821
    from mcp.server import MCPServer  # lazy: keeps cold start low

    cfg = load_config()
    # fail-fast validation: cache dir reachable, providers resolvable
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    mcp = MCPServer(
        "webintel",
        version="0.1.0",
        instructions=("web-intelligence tools for evidence work over MCP. Outputs are "
                      "compact JSON with short keys. Evidence spans are verbatim quotes "
                      "with url + fetch timestamp. No relevance scores are returned "
                      "(uncalibrated). Pick deep_research for multi-step questions; "
                      "web_search for direct lookups; extract_url (url, query) to read "
                      "a specific page. Keep max_tokens small unless you need more."),
    )

    # engine constructed on first use (lazy) so tools/list stays instant
    state: dict = {}

    def engine():
        if "pool" not in state:
            cache = Cache(cfg.cache_dir / "cache.sqlite3")
            pool = HttpPool(cfg)
            state["pool"] = pool
            state["cache"] = cache
            state["search"] = SearchEngine(cfg, pool)
        return state

    # warm up heavy imports in the background so the FIRST tool call doesn't pay
    # the trafilatura/lxml import cost (R3 cold-start); tools/list stays instant.
    threading.Thread(target=_warm_imports, daemon=True).start()

    @mcp.tool()
    async def web_search(
        query: str,
        max_results: int = 5,
        max_tokens: int = 600,
        freshness_days: int = 0,
        allowed_domains: list[str] | None = None,
    ) -> dict:
        """Search live web. Args: query; max_results<=10 (default 5); max_tokens cap
        (600 default, caller may lower; raise up to 1200 for more); freshness_days>0
        restricts to recent; allowed_domains limits to up-to-4 domains[].
        Returns {status:'ok'|'no_reliable_result', q, r:[{u,t,s,d?}], prov, note}.
        NOTE: prov in output lists each provider's status and latency for debugging."""
        if not query or not isinstance(query, str):
            return {"status": "error", "note": "query must be a non-empty string"}
        mr = max(3, min(int(max_results or 5), 10))
        mt = max(150, min(int(max_tokens or 600), 1200))
        fr = int(freshness_days or 0) or None
        e = engine()
        return await e["search"].web_search(
            query.strip(), max_results=mr, freshness=fr,
            domains=[d.strip() for d in (allowed_domains or []) if d.strip()],
            max_tokens=mt, cache=e["cache"],
            cache_key=f"ws:{query.strip()}|{mr}|{fr}|{'-'.join(sorted(allowed_domains or []))}|{mt}")

    @mcp.tool()
    async def extract_url(
        url: str,
        query: str = "",
        max_tokens: int = 1500,
        full: bool = False,
    ) -> dict:
        """Extract a web page's content. u=url required. query given = return the
        page's top chunks scored for the query (cheap 2-stage retrieval); full=true
        = return whole main content (costs as much as asked in max_tokens).
        Returns {status:'ok'|'no_content'|'thin_content_js'|'blocked'|'unreachable'|
        'unsupported_type', u, fetched_at, x:[{sec, span}], t?, date?, note}.
        Every x.span is a verbatim quote from that exact url at fetched_at."""
        if not url or not isinstance(url, str):
            return {"status": "error", "note": "url must be a non-empty string"}
        mt = max(200, min(int(max_tokens or 1500), full and 12000 or 3000))
        e = engine()
        return await _extract_url(e["pool"], e["cache"], cfg, url,
                                  query=query or None, full=bool(full),
                                  max_tokens=mt)

    @mcp.tool()
    async def crawl_website(
        url: str,
        max_pages: int = 5,
        max_depth: int = 1,
        map_only: bool = False,
        max_tokens: int = 4000,
    ) -> dict:
        """Crawl a site (same-domain only, robots.txt respected). url root or any
        page; max_pages<=25 (default 5); max_depth<=4 (0=url only);
        map_only=true returns just the URL tree (cheapest map of a site).
        Strict deadlines; budgeted; partial results if cap hit."""
        if not url or not isinstance(url, str):
            return {"status": "error", "note": "url must be a non-empty string"}
        e = engine()
        return await _crawl_website(e["pool"], e["cache"], cfg, url,
                                    max_pages=max_pages, max_depth=max_depth,
                                    map_only=bool(map_only), max_tokens=max_tokens,
                                    deadline=30.0)

    @mcp.tool()
    async def deep_research(
        question: str,
        max_searches: int = 3,
        max_pages: int = 6,
        max_tokens: int = 4000,
    ) -> dict:
        """Run bounded research: search -> rank -> extract -> gap-driven rounds, all
        server-side, no LLM. question required. Returns {status:'ok'|
        'partial_budget'|'no_reliable_result', q, terms, evidence:[{x,u,sec,ts}],
        gaps, budget:{searches,pages}, ms}. evidence spans are verbatim quotes.
        Use for questions needing several sources; keep max_tokens near 4000."""
        if not question or not isinstance(question, str):
            return {"status": "error", "note": "question must be a non-empty string"}
        e = engine()
        return await _deep_research(e["search"], e["pool"], e["cache"], cfg, question.strip(),
                                    max_searches=max(1, min(int(max_searches or 3), 6)),
                                    max_pages=max(2, min(int(max_pages or 6), 15)),
                                    max_tokens=max(800, min(int(max_tokens or 4000), 10000)))

    return mcp, cfg


async def serve_stdio():
    mcp, cfg = build_app()
    await mcp.run_stdio_async()


def main():  # python -m webintel
    # stdio transport: stdout is the protocol channel. Structural logs -> stderr only.
    t0 = time.perf_counter()
    try:
        build_app
        from mcp.server import MCPServer  # noqa: F401
        mcp, cfg = build_app()
        mcp.run("stdio")  # SDK-managed loop; supports anyio across all transports
    except KeyboardInterrupt:
        sys.stderr.write("webintel: shutdown (KeyboardInterrupt)\n")
    finally:
        sys.stderr.write(f"webintel server runtime {time.perf_counter() - t0:.2f}s\n")


if __name__ == "__main__":
    main()
