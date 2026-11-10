"""Typed, validated configuration. All values are overridable by environment."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .tenancy import (
    normalise_api_keys,
    normalise_tenant_rate_limits,
    parse_api_keys,
    parse_tenant_rate_limits,
)

_ALLOWED_PROVIDERS = {
    "ddg",
    "brave",
    "tavily",
    "searxng",
    "bing",
    "yahoo",
    "mwmbl",
    "wikipedia",
    "stackexchange",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEBLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- search providers -------------------------------------------------
    # Comma-separated order. Supported: ddg, mwmbl, brave, tavily, searxng,
    # bing, yahoo, wikipedia, stackexchange
    # The default chain is deliberately redundant: keyless HTML providers come
    # and go (DuckDuckGo blocks or timeouts entire networks, Bing/Yahoo
    # rate-limit), so a single-provider default silently degrades to two weak
    # sources. mwmbl and wikipedia are always available; bing and yahoo add
    # mainstream index coverage and are tried after them; stackexchange is a
    # narrow technical supplement. Provider health is tracked in the router, so
    # an endpoint that is failing is skipped for a cooldown window instead of
    # stalling every query.
    search_providers: str = "mwmbl,wikipedia,bing,yahoo"
    # Providers tried only when the primary fuse leaves fewer than k accepted
    # results. Narrow supplements (stackexchange for technical questions) add
    # coverage when the general index is thin without competing for top-k
    # precision on every query.
    supplement_providers: str = "stackexchange"
    # Accept both the prefixed settings names and the vendor-standard names
    # commonly placed in `.env` files. The prefixed spelling wins when both are
    # present, so deployment-specific overrides stay unambiguous.
    brave_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBLENS_BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"),
    )
    tavily_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBLENS_TAVILY_API_KEY", "TAVILY_API_KEY"),
    )
    searxng_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBLENS_SEARXNG_URL", "SEARXNG_URL", "SEARXNG_BASE_URL"),
    )
    # Optional Stack Apps key. The Stack Exchange API is usable without one
    # (300 requests/day per IP); a key raises that quota for deployments that
    # field many technical queries.
    stackexchange_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBLENS_STACKEXCHANGE_KEY", "STACKEXCHANGE_KEY"),
    )
    # When a Tavily key is configured, prepend the hosted Tavily provider even
    # if ``search_providers`` does not mention it. Tavily is the fastest and
    # most reliable participant in the fuse; the keyless providers still run as
    # the free backstop. Set False to keep a strictly keyless chain even when a
    # key is present (for example to measure keyless-only quality).
    auto_include_tavily: bool = True
    search_mode: Literal["fallback", "fuse"] = "fuse"
    provider_timeout_s: float = 3.5
    # Quality-guarded early stop for the hosted fast path. Once a Tavily hit is
    # in the accepted pool and the Tavily subset alone holds at least
    # ``k + fuse_early_min_extra`` distinct results across at least
    # ``fuse_early_min_domains`` registrable domains, the router waits
    # ``fuse_grace_s`` for in-flight providers and then cancels the rest. A
    # keyless pool never early-stops: the confirmatory n=40 paired run showed a
    # P@5 loss beyond the pre-registered margin when slow keyless providers were
    # cut. Set ``fuse_soft_timeout_s`` to 0 to always wait for every provider.
    fuse_soft_timeout_s: float = Field(default=2.0, ge=0.0, le=30.0)
    fuse_early_min_extra: int = Field(default=0, ge=0, le=20)
    fuse_early_min_domains: int = Field(default=3, ge=1, le=50)
    fuse_grace_s: float = Field(default=0.25, ge=0.0, le=5.0)
    # Short-lived cache for fused provider results. Repeated queries (for
    # example a synthesis follow-up hop) reuse the same ranked hit list instead
    # of re-hitting free providers. 0 disables it; provider failures are never
    # cached.
    search_cache_ttl_s: int = Field(default=300, ge=0)
    # Curated "primary source" hints map well-known topics to official URLs.
    # They improve real-world results, but they are author-curated, so any
    # evaluation whose relevance labels were written by the same author is
    # contaminated when they are on. Disable for honest head-to-head
    # comparisons against other search engines.
    use_official_source_hints: bool = True

    # --- network limits ---------------------------------------------------
    connect_timeout_s: float = 4.0
    read_timeout_s: float = 12.0
    total_timeout_s: float = 20.0
    research_fetch_timeout_s: float = 8.0
    max_response_bytes: int = 4_000_000
    max_redirects: int = 5
    max_concurrency: int = 8
    per_host_concurrency: int = 2
    user_agent: str = (
        "WebLens/0.1 (+https://github.com/local/weblens) "
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    )
    accept_language: str = "en-US,en;q=0.9"

    # --- security ---------------------------------------------------------
    allow_private_networks: bool = False
    block_hosts: str = ""  # comma-separated deny list (suffix match)
    allow_hosts: str = ""  # outbound SSRF allowlist (optional); empty = any public host

    # X-Forwarded-For handling. Default False: key rate limits on the ASGI peer
    # address and ignore spoofed XFF values. Set True when running behind a
    # trusted reverse proxy that appends the real client IP.
    trust_proxy_headers: bool = False

    # Inbound MCP HTTP transport Host/Origin validation (DNS-rebinding defence).
    # Loopback only by default. Set WEBLENS_ALLOWED_HOSTS / WEBLENS_ALLOWED_ORIGINS
    # (comma-separated) to add public hostnames. Use "*" for explicit opt-out.
    allowed_hosts: str = "localhost,127.0.0.1,[::1]"
    allowed_origins: str = ""
    allow_browser: bool = False
    browser_timeout_s: float = 20.0

    # --- cache ------------------------------------------------------------
    cache_dir: Path = Field(default_factory=lambda: Path.home() / ".weblens")
    cache_enabled: bool = True
    # Logical payload cap (compressed value + metadata bytes), not SQLite file
    # size. 0 disables eviction.
    cache_max_bytes: int = Field(default=512 * 1024 * 1024, ge=0)
    page_cache_ttl_s: int = 86_400
    robots_cache_ttl_s: int = 3_600
    # Fail-open by default: missing/malformed robots.txt still allows crawling.
    # Set True to deny all on any robots.txt fetch/parse failure.
    robots_fail_closed: bool = False
    # Optional shared cache for multi-instance deployments. SQLite remains the
    # zero-dependency default; Redis is selected explicitly and fails open as a
    # cache miss rather than breaking a request.
    cache_backend: Literal["sqlite", "redis"] = "sqlite"
    # When a live page fetch fails (timeout, protocol error, retryable 5xx), an
    # expired cached copy may still be served for this many seconds. Stale
    # responses keep their original fetched_at and are marked stale, so
    # provenance is never rewritten. 0 disables stale fallback.
    cache_stale_grace_s: int = Field(default=604_800, ge=0)
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", repr=False)
    redis_namespace: str = "weblens"
    redis_socket_timeout_s: float = Field(default=1.0, gt=0, le=30)
    redis_max_connections: int = Field(default=32, ge=1, le=1000)

    # --- output budgets ---------------------------------------------------
    max_search_tokens: int = 600
    max_extract_tokens: int = 1_500
    max_research_tokens: int = 2_000
    default_results: int = 5

    # Optional search snippet enrichment. 0 keeps search on the fast path;
    # set it to 1-5 to replace the first N provider blurbs with a relevant
    # passage from the page. The trade-off is a bounded number of parallel
    # page fetches, so it is opt-in rather than a silent latency increase.
    search_enrich_top: int = Field(default=0, ge=0, le=10)
    search_enrich_timeout_s: float = Field(default=2.5, gt=0, le=30)

    # --- local dense retrieval -------------------------------------------
    # Crawl2RAG uses BM25 by default. When a local all-MiniLM-L6-v2 ONNX model
    # directory is available, hybrid retrieval adds dense candidates and fuses
    # them with BM25. The model is never downloaded implicitly.
    embedding_enabled: bool = True
    embedding_model_dir: Path | None = None
    embedding_max_length: int = Field(default=256, ge=32, le=512)
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    embedding_max_scan: int = Field(default=50_000, ge=1)

    # --- server -----------------------------------------------------------
    http_host: str = "127.0.0.1"
    # Render, Cloudflare Containers, Google Cloud Run and Heroku all inject the
    # listen port as $PORT and route only to that port. Reading it here means the
    # image binds where the platform sends traffic; without it the server bound
    # 8765 and every platform health check failed. Explicit WEBLENS_HTTP_PORT
    # still wins because it is the more specific name.
    http_port: int = Field(
        default=8765,
        validation_alias=AliasChoices("WEBLENS_HTTP_PORT", "PORT"),
    )
    http_token: str | None = Field(default=None, repr=False)
    # JSON {"tenant": "key"} or comma-separated tenant=key pairs. The legacy
    # single http_token maps to the "default" tenant.
    api_keys: str = Field(default="", repr=False)
    tenant_rate_limits: str = ""
    http_rate_limit_per_minute: int = Field(default=120, ge=1, le=100_000)
    http_auth_failure_limit_per_minute: int = Field(default=60, ge=1, le=100_000)
    log_level: str = "INFO"
    mcp_profile: Literal["core", "research", "full"] = "core"

    @field_validator("search_providers")
    @classmethod
    def _providers(cls, v: str) -> str:
        names = [p.strip().lower() for p in v.split(",") if p.strip()]
        bad = [p for p in names if p not in _ALLOWED_PROVIDERS]
        if bad:
            raise ValueError(f"unknown search provider(s): {bad}; allowed={sorted(_ALLOWED_PROVIDERS)}")
        return ",".join(names)

    @field_validator("supplement_providers")
    @classmethod
    def _supplement_providers(cls, v: str) -> str:
        names = [p.strip().lower() for p in v.split(",") if p.strip()]
        bad = [p for p in names if p not in _ALLOWED_PROVIDERS]
        if bad:
            raise ValueError(f"unknown search provider(s): {bad}; allowed={sorted(_ALLOWED_PROVIDERS)}")
        return ",".join(names)

    @field_validator("cache_dir", mode="after")
    @classmethod
    def _expand_cache_dir(cls, v: Path) -> Path:
        # A literal "~" in WEBLENS_CACHE_DIR must not create a "~" directory in
        # the working directory.
        return v.expanduser()

    @field_validator("embedding_model_dir", mode="after")
    @classmethod
    def _expand_embedding_model_dir(cls, v: Path | None) -> Path | None:
        return v.expanduser() if v is not None else None

    @field_validator("api_keys")
    @classmethod
    def _api_keys(cls, v: str) -> str:
        return normalise_api_keys(v)

    @field_validator("tenant_rate_limits")
    @classmethod
    def _tenant_rate_limits(cls, v: str) -> str:
        return normalise_tenant_rate_limits(v)

    @field_validator("redis_namespace")
    @classmethod
    def _redis_namespace(cls, v: str) -> str:
        value = (v or "").strip()
        if not value or any(ch.isspace() or ch == ":" for ch in value):
            raise ValueError("redis_namespace must be non-empty and contain no whitespace or ':'")
        return value

    @property
    def provider_list(self) -> list[str]:
        return [p for p in self.search_providers.split(",") if p]

    @property
    def supplement_list(self) -> list[str]:
        return [p for p in self.supplement_providers.split(",") if p]

    @property
    def host_allowlist(self) -> tuple[str, ...]:
        """Outbound hosts permitted by DestinationPolicy when not empty."""
        return tuple(h.strip().lower() for h in self.allow_hosts.split(",") if h.strip())

    @property
    def mcp_host_allowlist(self) -> tuple[str, ...]:
        """Inbound Host header values accepted by the MCP HTTP transport."""
        return tuple(h.strip().lower() for h in self.allowed_hosts.split(",") if h.strip())

    @property
    def origin_allowlist(self) -> tuple[str, ...]:
        """Origins permitted by the MCP DNS-rebinding middleware."""
        return tuple(o.strip().lower() for o in self.allowed_origins.split(",") if o.strip())

    @property
    def denylist(self) -> tuple[str, ...]:
        return tuple(h.strip().lower() for h in self.block_hosts.split(",") if h.strip())

    # Backward-compatible alias: outbound SSRF allowlist.
    @property
    def allowlist(self) -> tuple[str, ...]:
        return self.host_allowlist

    @property
    def api_key_map(self) -> dict[str, str]:
        return parse_api_keys(self.api_keys)

    @property
    def tenant_rate_limit_map(self) -> dict[str, int]:
        return parse_tenant_rate_limits(self.tenant_rate_limits)

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings


def reset_settings() -> None:
    """Test helper: drop the cached settings object."""
    global _settings
    _settings = None
