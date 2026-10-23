"""
Engine Configuration Module
Loads configuration from environment variables with safe, audited defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    # Server metadata
    server_name: str = os.getenv("MCP_SERVER_NAME", "personal-web-intelligence")
    server_version: str = os.getenv("MCP_SERVER_VERSION", "1.0.0")
    host: str = os.getenv("MCP_HOST", "127.0.0.1")
    port: int = int(os.getenv("MCP_PORT", "8765"))

    # Search provider configuration
    default_search_provider: str = os.getenv("DEFAULT_SEARCH_PROVIDER", "wikipedia")
    brave_api_key: str = os.getenv("BRAVE_SEARCH_API_KEY", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    exa_api_key: str = os.getenv("EXA_API_KEY", "")
    searxng_base_url: str = os.getenv("SEARXNG_BASE_URL", "")

    # Token Budgets (R1 Prime Requirement)
    default_search_tokens: int = int(os.getenv("DEFAULT_SEARCH_TOKEN_BUDGET", "600"))
    default_extract_tokens: int = int(os.getenv("DEFAULT_EXTRACT_TOKEN_BUDGET", "1200"))
    default_research_tokens: int = int(os.getenv("DEFAULT_DEEP_RESEARCH_TOKEN_BUDGET", "2000"))

    # Latency & Security Constraints (R3 & Phase 5)
    connect_timeout: float = float(os.getenv("HTTP_CONNECT_TIMEOUT_SECONDS", "8.0"))
    read_timeout: float = float(os.getenv("HTTP_READ_TIMEOUT_SECONDS", "12.0"))
    max_response_bytes: int = int(os.getenv("MAX_HTTP_RESPONSE_BYTES", str(5 * 1024 * 1024))) # 5 MB
    max_crawl_pages: int = int(os.getenv("MAX_CRAWL_PAGES", "15"))
    max_crawl_depth: int = int(os.getenv("MAX_CRAWL_DEPTH", "3"))

    # Browser Fallback
    enable_browser_fallback: bool = os.getenv("ENABLE_BROWSER_FALLBACK", "true").lower() in ("true", "1", "yes")
    browser_binary_path: str = os.getenv("BROWSER_BINARY_PATH", "")

    # User Agent
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

CONFIG = EngineConfig()
