from __future__ import annotations

from pathlib import Path

import pytest

from weblens.config import Settings


def test_cache_dir_expands_home():
    settings = Settings(cache_dir="~/.weblens-test")
    assert settings.cache_dir == Path.home() / ".weblens-test"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="unknown search provider"):
        Settings(search_providers="ddg,not-a-provider")


def test_provider_order_is_normalized():
    settings = Settings(search_providers=" DDG, Mwmbl ,wikipedia ")
    assert settings.provider_list == ["ddg", "mwmbl", "wikipedia"]


def test_optional_yahoo_provider_is_accepted():
    settings = Settings(search_providers="ddg,yahoo")
    assert settings.provider_list == ["ddg", "yahoo"]


def test_vendor_standard_secret_names_are_accepted(monkeypatch):
    monkeypatch.delenv("WEBLENS_TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("WEBLENS_BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("WEBLENS_SEARXNG_URL", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-test")
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://searx.example")

    settings = Settings(_env_file=None)

    assert settings.tavily_api_key == "tvly-test"
    assert settings.brave_api_key == "brave-test"
    assert settings.searxng_url == "https://searx.example"


def test_prefixed_secret_name_wins_when_both_are_present(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "unprefixed")
    monkeypatch.setenv("WEBLENS_TAVILY_API_KEY", "prefixed")

    settings = Settings(_env_file=None)

    assert settings.tavily_api_key == "prefixed"
