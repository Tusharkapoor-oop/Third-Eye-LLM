"""Configuration module for the MCP Web Intelligence Engine.

Loads settings from environment variables and .env with production defaults,
domain authority lists, anti-bot signatures, and timeout controls.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load local .env if present
load_dotenv(Path(".env"))
load_dotenv(Path("weblens/.env"))


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration."""

    # Server Metadata
    server_name: str = os.getenv("MCP_SERVER_NAME", "MyWebEngine")
    server_version: str = os.getenv("MCP_SERVER_VERSION", "2.0.0")
    host: str = os.getenv("MCP_HOST", "127.0.0.1")
    port: int = int(os.getenv("MCP_PORT", "8765"))

    # API Keys
    tavily_api_key: str = (
        os.getenv("TAVILY_API_KEY", "")
        or os.getenv("WEBLENS_TAVILY_API_KEY", "")
    )
    gemini_api_key: str = (
        os.getenv("GEMINI_API_KEY", "")
        or os.getenv("GOOGLE_API_KEY", "")
        or os.getenv("GEMINI_API_KEY_1", "")
        or os.getenv("GEMINI_API_KEY_2", "")
    )
    searxng_url: str = (
        os.getenv("SEARXNG_URL", "")
        or os.getenv("SEARXNG_BASE_URL", "")
        or "http://localhost:8080"
    )

    # Timeouts & Limits
    connect_timeout_s: float = float(os.getenv("HTTP_CONNECT_TIMEOUT_SECONDS", "5.0"))
    read_timeout_s: float = float(os.getenv("HTTP_READ_TIMEOUT_SECONDS", "12.0"))
    page_timeout_ms: int = int(os.getenv("PAGE_TIMEOUT_MS", "15000"))
    max_response_bytes: int = int(os.getenv("MAX_HTTP_RESPONSE_BYTES", str(10 * 1024 * 1024)))
    max_crawl_pages: int = int(os.getenv("MAX_CRAWL_PAGES", "20"))
    max_crawl_depth: int = int(os.getenv("MAX_CRAWL_DEPTH", "2"))

    # Cache Settings
    cache_db_path: str = os.getenv("CACHE_DB_PATH", "./.omni_cache.db")
    default_cache_ttl_hours: float = float(os.getenv("CACHE_TTL_HOURS", "24.0"))

    # Playwright / Browser Engine Settings
    headless: bool = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
    user_data_dir: str = os.getenv("CRAWL4AI_USER_DATA_DIR", "./.crawl4ai_profile")
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    # Token & Passage Extraction Defaults
    default_search_tokens: int = int(os.getenv("DEFAULT_SEARCH_TOKEN_BUDGET", "600"))
    default_extract_tokens: int = int(os.getenv("DEFAULT_EXTRACT_TOKEN_BUDGET", "1200"))
    default_research_tokens: int = int(os.getenv("DEFAULT_DEEP_RESEARCH_TOKEN_BUDGET", "3000"))
    default_chunks_per_source: int = 3
    target_chunk_chars: int = 500

    # Domain Authority Boosts
    tier1_domains: tuple[str, ...] = (
        "docs.python.org",
        "developer.mozilla.org",
        "github.com",
        "stackoverflow.com",
        "arxiv.org",
        "pypi.org",
        "en.wikipedia.org",
        "wikipedia.org",
        "reuters.com",
        "apnews.com",
        "nature.com",
        "ieee.org",
        "nih.gov",
        "cdc.gov",
        "who.int",
        "w3.org",
        "ietf.org",
        "rust-lang.org",
        "go.dev",
        "nodejs.org",
    )

    tier2_domains: tuple[str, ...] = (
        "medium.com",
        "dev.to",
        "techcrunch.com",
        "theverge.com",
        "arstechnica.com",
        "bleepingcomputer.com",
        "wired.com",
        "bloomberg.com",
        "ft.com",
        "wsj.com",
        "bbc.com",
    )

    # Low-Signal / Content Farm Penalty Domains
    penalized_domains: tuple[str, ...] = (
        "geeksforgeeks.org",
        "w3schools.com",
        "javatpoint.com",
        "tutorialspoint.com",
        "guru99.com",
        "byjus.com",
    )

    # Anti-Bot & WAF Signatures (Case-Insensitive)
    waf_signatures: tuple[str, ...] = (
        "just a moment...",
        "verify you are human",
        "checking your browser before accessing",
        "attention required! | cloudflare",
        "cloudflare ray id",
        "enable javascript and cookies to continue",
        "access denied - datadome",
        "datadome",
        "akamai ghost",
        "request blocked by security policy",
        "bot detection",
        "cf-turnstile",
        "challenges.cloudflare.com",
    )

    # SPA Skeleton Markers
    spa_markers: tuple[str, ...] = (
        '<div id="root"></div>',
        "<div id=\"root\"></div>",
        '<div id="__next"></div>',
        "<div id=\"__next\"></div>",
        '<div id="app"></div>',
        "<div id=\"app\"></div>",
    )


CONFIG = AppConfig()
