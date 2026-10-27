from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from weblens.cache import Cache
from weblens.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="ddg",
    )


@pytest.fixture
def cache(settings):
    c = Cache(settings)
    yield c
    c.close()
