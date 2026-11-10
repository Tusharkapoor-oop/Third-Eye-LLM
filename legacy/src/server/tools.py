"""
MCP Tool Specifications and Compact Schema Definitions.
Engineered for minimal schema token footprint while maintaining complete parameter clarity.
"""

from __future__ import annotations

# Compact Tool Schemas adhering to JSON Schema Draft 7 / 2020-12
TOOL_DEFINITIONS = [
    {
        "name": "web_search",
        "description": "Search the live web. Returns ranked titles, URLs, and snippets within a token budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "count": {"type": "integer", "description": "Max results (default 5, max 10)", "default": 5},
                "time_filter": {"type": "string", "enum": ["day", "week", "month", "year"], "description": "Recency filter"},
                "domains": {"type": "array", "items": {"type": "string"}, "description": "Restrict to specific domains"},
                "max_tokens": {"type": "integer", "description": "Hard token cap (default 600)", "default": 600}
            },
            "required": ["query"]
        }
    },
    {
        "name": "extract_url",
        "description": "Extract content from a URL. By default returns query-relevant passages with exact text spans.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target webpage or PDF URL"},
                "query": {"type": "string", "description": "Optional question to retrieve only relevant passages"},
                "mode": {"type": "string", "enum": ["passages", "full"], "description": "Default 'passages' (token-efficient) or 'full'", "default": "passages"},
                "max_tokens": {"type": "integer", "description": "Hard token cap (default 1200)", "default": 1200},
                "render_js": {"type": "boolean", "description": "Enable headless browser for JS-only SPAs", "default": False}
            },
            "required": ["url"]
        }
    },
    {
        "name": "crawl_website",
        "description": "Bounded recursive crawl of a website starting from a seed URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Seed URL"},
                "max_depth": {"type": "integer", "description": "Max link depth (default 1, max 3)", "default": 1},
                "max_pages": {"type": "integer", "description": "Max pages (default 5, max 15)", "default": 5},
                "allowed_paths": {"type": "array", "items": {"type": "string"}, "description": "Allowed URL path prefixes"},
                "max_tokens_per_page": {"type": "integer", "description": "Token cap per page", "default": 800}
            },
            "required": ["url"]
        }
    },
    {
        "name": "web_map",
        "description": "Discovers domain topology and sitemap URLs without downloading full pages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Domain or root URL"},
                "limit": {"type": "integer", "description": "Max URLs to discover (default 30, max 100)", "default": 30}
            },
            "required": ["url"]
        }
    },
    {
        "name": "deep_research",
        "description": "Autonomous multi-query research loop. Gathers evidence, cross-corroborates facts, and reports uncertainties.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Research question"},
                "max_searches": {"type": "integer", "description": "Max query variations (default 3, max 6)", "default": 3},
                "max_pages": {"type": "integer", "description": "Max pages to inspect (default 5, max 10)", "default": 5},
                "time_filter": {"type": "string", "enum": ["day", "week", "month", "year"], "description": "Recency filter"},
                "max_tokens": {"type": "integer", "description": "Hard token cap (default 2000)", "default": 2000}
            },
            "required": ["question"]
        }
    }
]
