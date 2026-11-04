"""
Engine Configuration Module
Loads configuration from environment variables with safe, audited defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bootstrap_env() -> None:
    for env_path in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_bootstrap_env()


def _budget_cap() -> float:
    value = os.getenv("BUDGET_CAP", "0").strip().casefold()
    if value in {"unlimited", "inf", "infinite", "no_limit"}:
        return float("inf")
    try:
        return float(value or "0")
    except ValueError:
        return 0.0


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
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_QUERY_MODEL", "gemini-2.5-flash")
    enable_query_expansion: bool = os.getenv("ENABLE_QUERY_EXPANSION", "false").lower() in ("true", "1", "yes")
    tavily_extract_fallback: bool = os.getenv("ENABLE_TAVILY_EXTRACT_FALLBACK", "false").lower() in ("true", "1", "yes")
    enable_tavily_fallback: bool = os.getenv("ENABLE_TAVILY_FALLBACK", "false").lower() in ("true", "1", "yes")

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
    browser_timeout: float = float(os.getenv("BROWSER_TIMEOUT_SECONDS", "12.0"))
    browser_profile_dir: str = os.getenv("BROWSER_PROFILE_DIR", ".crawl4ai_profile")
    max_concurrent_fetches: int = int(os.getenv("MAX_CONCURRENT_FETCHES", "8"))
    arena_budget_cap: float = _budget_cap()

    # User Agent
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

CONFIG = EngineConfig()
