"""Typed, validated configuration. All values are overridable by environment."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEBLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- search providers -------------------------------------------------
    # Comma-separated order. Supported: ddg, mwmbl, brave, tavily, searxng, bing, wikipedia
    # Bing is optional and documented as degraded: its retired-API HTML fallback
    # has returned unsafe, off-topic results and is not part of the default chain.
    search_providers: str = "ddg,mwmbl,wikipedia"
    brave_api_key: str | None = None
    tavily_api_key: str | None = None
    searxng_url: str | None = None
    search_mode: Literal["fallback", "fuse"] = "fuse"
    provider_timeout_s: float = 3.5

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
    allowed_hosts: str = ""  # optional comma-separated allowlist; empty = all public
    block_hosts: str = ""  # comma-separated deny list (suffix match)
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

    # --- output budgets ---------------------------------------------------
    max_search_tokens: int = 600
    max_extract_tokens: int = 1_500
    max_research_tokens: int = 2_000
    default_results: int = 5

    # --- server -----------------------------------------------------------
    http_host: str = "127.0.0.1"
    http_port: int = 8765
    http_token: str | None = None
    log_level: str = "INFO"

    @field_validator("search_providers")
    @classmethod
    def _providers(cls, v: str) -> str:
        allowed = {"ddg", "brave", "tavily", "searxng", "bing", "mwmbl", "wikipedia"}
        names = [p.strip().lower() for p in v.split(",") if p.strip()]
        bad = [p for p in names if p not in allowed]
        if bad:
            raise ValueError(f"unknown search provider(s): {bad}; allowed={sorted(allowed)}")
        return ",".join(names)

    @field_validator("cache_dir", mode="after")
    @classmethod
    def _expand_cache_dir(cls, v: Path) -> Path:
        # A literal "~" in WEBLENS_CACHE_DIR must not create a "~" directory in
        # the working directory.
        return v.expanduser()

    @property
    def provider_list(self) -> list[str]:
        return [p for p in self.search_providers.split(",") if p]

    @property
    def allowlist(self) -> tuple[str, ...]:
        return tuple(h.strip().lower() for h in self.allowed_hosts.split(",") if h.strip())

    @property
    def denylist(self) -> tuple[str, ...]:
        return tuple(h.strip().lower() for h in self.block_hosts.split(",") if h.strip())

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
