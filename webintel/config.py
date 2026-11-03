"""Configuration from environment. Fail-fast validation at startup (PHASE 8)."""
from __future__ import annotations

import os
import pathlib
import secrets
from dataclasses import dataclass, field
from typing import List, Optional

APP_NAME = "webintel"


@dataclass
class SearchProviderConfig:
    order: List[str]              # ordered provider ids, first = preferred
    tavily_key: Optional[str]
    brave_key: Optional[str]
    searxng_url: Optional[str]


@dataclass
class Config:
    search: SearchProviderConfig
    cache_dir: pathlib.Path
    ttl_search: int
    ttl_fetch: int
    ttl_extract: int
    http_timeout_search: float
    http_timeout_fetch: float
    http_timeout_browser: Optional[str]
    max_response_bytes: int
    max_redirects: int
    max_concurrency: int
    crawl_default_pages: int
    crawl_max_pages: int
    allow_private_net: bool        # TEST ONLY - disables SSRF protection
    transport: str                 # stdio | http
    http_host: str
    http_port: int
    http_token: Optional[str]      # required when binding non-loopback
    js_render: bool
    default_max_results: int
    # --- quality pipeline (all defaulted so existing call sites stay valid) ---
    gemini_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"
    browser_profile_dir: str = ""
    browser_timeout_ms: int = 25000
    chunks_per_source: int = 3
    max_page_chars: int = 0        # 0 = never blind-truncate a page


_DOTENV_LOADED = False


def _load_dotenv() -> None:
    """Load ``.env`` from the working directory once, without overriding real env.

    The MCP client normally injects environment variables, but CLI tools such as
    ``quality_arena.py`` and ``python -m webintel`` are frequently launched from a
    plain shell. This keeps both paths identical and never prints values.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    candidates = [pathlib.Path.cwd() / ".env", pathlib.Path(__file__).resolve().parent.parent / ".env"]
    for path in candidates:
        try:
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            return
        except OSError:
            continue


def _int(env: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(env)
    try:
        v = int(raw) if raw is not None else default
    except ValueError:
        raise SystemExit(f"config error: {env} must be an integer")
    return max(lo, min(hi, v))


def _float(env: str, default: float, lo: float, hi: float) -> float:
    raw = os.environ.get(env)
    try:
        v = float(raw) if raw is not None else default
    except ValueError:
        raise SystemExit(f"config error: {env} must be a number")
    return max(lo, min(hi, v))


def _data_dir() -> pathlib.Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or "."
    d = pathlib.Path(base) / APP_NAME if base != "." else pathlib.Path(os.environ.get("WEBINTEL_CACHE_DIR", "./.webintel"))
    if os.environ.get("WEBINTEL_CACHE_DIR"):
        d = pathlib.Path(os.environ["WEBINTEL_CACHE_DIR"])
    return d


def load_config() -> Config:
    _load_dotenv()
    # Provider order: explicit config wins; else auto discovery by available keys.
    explicit = os.environ.get("WEBINTEL_PROVIDER_ORDER", "auto").strip()
    tavily_key = os.environ.get("TAVILY_API_KEY") or None
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY") or os.environ.get("BRAVE_API_KEY") or None
    searxng_url = os.environ.get("SEARXNG_URL") or None
    if explicit.lower() == "auto":
        # Local-first discovery. Tavily is deliberately NOT a primary provider:
        # it is reserved for the zero-result rescue path and Tier 3 extraction,
        # so a local-vs-Tavily comparison measures two independent systems.
        # Add it explicitly with WEBINTEL_PROVIDER_ORDER=tavily,... if wanted.
        order = []
        if searxng_url:
            order.append("searxng")
        if brave_key:
            order.append("brave")
        order.append("bing_rss")          # keyless always available
        seen = set()
        order = [p for p in order if not (p in seen or seen.add(p))]
    else:
        order = [p.strip().lower() for p in explicit.split(",") if p.strip()]
        known = {"bing_rss", "tavily", "brave", "searxng", "duckduckgo"}
        for p in order:
            if p not in known:
                raise SystemExit(
                    f"config error: WEBINTEL_PROVIDER_ORDER contains unknown provider '{p}'. "
                    f"Known: {sorted(known)}"
                )
        if tavily_key is None:
            order = [p for p in order if p != "tavily"]
        if brave_key is None:
            order = [p for p in order if p != "brave"]
        if searxng_url is None:
            order = [p for p in order if p != "searxng"]
        if not order:
            order = ["bing_rss"]

    transport = os.environ.get("WEBINTEL_TRANSPORT", "stdio").lower()
    if transport not in ("stdio", "http"):
        raise SystemExit("config error: WEBINTEL_TRANSPORT must be 'stdio' or 'http'")
    host = os.environ.get("WEBINTEL_HTTP_HOST", "127.0.0.1")
    port = _int("WEBINTEL_HTTP_PORT", 33117, 1, 65535)
    http_token = os.environ.get("WEBINTEL_HTTP_TOKEN") or None
    if not http_token and transport == "http" and host not in ("127.0.0.1", "localhost", "::1"):
        # Least privilege: non-loopback bind requires an explicit token; refuse to
        # start otherwise instead of silently exposing unauthenticated access.
        raise SystemExit(
            "config error: WEBINTEL_TRANSPORT=http on a non-loopback host requires "
            "WEBINTEL_HTTP_TOKEN (generate one, e.g. python -c 'import secrets;print(secrets.token_urlsafe(32))')"
        )
    decl_token = os.environ.get("WEBINTEL_HTTP_TOKEN") == ""
    if decl_token:
        raise SystemExit("config error: empty WEBINTEL_HTTP_TOKEN")

    allow_private = os.environ.get("WEBINTEL_ALLOW_PRIVATE_NET", "0") in ("1", "true", "yes")
    if allow_private:
        import sys
        print("WARNING: WEBINTEL_ALLOW_PRIVATE_NET=1 disables SSRF protection.TEST ONLY.",
              file=sys.stderr)

    return Config(
        search=SearchProviderConfig(order=order, tavily_key=tavily_key,
                                    brave_key=brave_key, searxng_url=searxng_url),
        cache_dir=_data_dir(),
        ttl_search=_int("WEBINTEL_TTL_SEARCH", 900, 0, 86400),
        ttl_fetch=_int("WEBINTEL_TTL_FETCH", 3600, 0, 259200),
        ttl_extract=_int("WEBINTEL_TTL_EXTRACT", 21600, 0, 604800),
        http_timeout_search=_float("WEBINTEL_HTTP_TIMEOUT_SEARCH", 8.0, 1.0, 30.0),
        http_timeout_fetch=_float("WEBINTEL_HTTP_TIMEOUT_FETCH", 15.0, 1.0, 60.0),
        http_timeout_browser=os.environ.get("WEBINTEL_HTTP_TIMEOUT_BROWSER"),
        max_response_bytes=_int("WEBINTEL_MAX_RESPONSE_BYTES", 3_000_000, 50_000, 15_000_000),
        max_redirects=_int("WEBINTEL_MAX_REDIRECTS", 6, 0, 15),
        max_concurrency=_int("WEBINTEL_MAX_CONCURRENCY", 6, 1, 16),
        crawl_default_pages=_int("WEBINTEL_CRAWL_DEFAULT_PAGES", 5, 1, 15),
        crawl_max_pages=_int("WEBINTEL_CRAWL_MAX_PAGES", 25, 1, 60),
        allow_private_net=allow_private,
        transport=transport,
        http_host=host,
        http_port=port,
        http_token=http_token,
        js_render=os.environ.get("WEBINTEL_JS_RENDER", "1") in ("1", "true", "yes"),
        default_max_results=_int("WEBINTEL_DEFAULT_MAX_RESULTS", 5, 1, 10),
        gemini_key=(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None),
        gemini_model=os.environ.get("WEBINTEL_GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_pro_model=os.environ.get("WEBINTEL_GEMINI_PRO_MODEL", "gemini-2.5-pro"),
        browser_profile_dir=os.environ.get(
            "WEBINTEL_BROWSER_PROFILE", str(_data_dir() / "chromium-profile")
        ),
        browser_timeout_ms=_int("WEBINTEL_BROWSER_TIMEOUT_MS", 25000, 3000, 90000),
        chunks_per_source=_int("WEBINTEL_CHUNKS_PER_SOURCE", 3, 1, 5),
        max_page_chars=_int("WEBINTEL_MAX_PAGE_CHARS", 0, 0, 200000),
    )


def new_token() -> str:
    return secrets.token_urlsafe(32)


_field = field  # keep import-cost trivial for dataclass reuse elsewhere
