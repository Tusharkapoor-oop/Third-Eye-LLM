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
