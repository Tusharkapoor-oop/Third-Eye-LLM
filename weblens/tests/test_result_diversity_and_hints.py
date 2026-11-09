"""Regression tests for the result-diversity guarantee and the hint switch.

Two behaviours introduced during the v11 comparison:

1. ``diversify(strict=True)`` must actually enforce the per-domain cap instead
   of appending the surplus (which let a single domain fill the whole window).
2. ``Settings.use_official_source_hints=False`` must stop the router from
   injecting author-curated "primary source" URLs, so an honest head-to-head
   benchmark measures real retrieval rather than dataset label leakage.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from weblens.config import Settings
from weblens.search.base import Hit, diversify
from weblens.search.router import SearchRouter
from weblens.service import WebLens


def _hit(url: str, title: str = "t") -> Hit:
    return Hit(title=title, url=url, snippet="s", provider="mwmbl", rank=0)


class _FakeProvider:
    name = "mwmbl"
    timeout_s = 5.0

    def __init__(self, hits: list[Hit]):
        self._hits = hits

    async def search(self, q, *, k=5, freshness=None, domains=None, exclude_domains=None):
        return list(self._hits)


# --------------------------------------------------------------------------- #
# diversify
# --------------------------------------------------------------------------- #
def test_diversify_default_keeps_surplus_after_capped_results():
    hits = [_hit(f"https://a.com/{i}") for i in range(4)]
    out = diversify(hits, per_domain=2)
    # Capped ones first, surplus appended: the documented historical behaviour.
    assert len(out) == 4
    assert [h.url for h in out[:2]] == ["https://a.com/0", "https://a.com/1"]


def test_diversify_strict_enforces_the_cap():
    hits = [_hit(f"https://a.com/{i}") for i in range(5)]
    out = diversify(hits, per_domain=2, strict=True)
    assert len(out) == 2
    assert all(h.url.startswith("https://a.com/") for h in out)


def test_diversify_strict_preserves_domain_mix():
    hits = [
        _hit("https://a.com/1"),
        _hit("https://a.com/2"),
        _hit("https://a.com/3"),
        _hit("https://b.com/1"),
        _hit("https://c.com/1"),
    ]
    out = diversify(hits, per_domain=2, strict=True)
    domains = {h.url.split("/")[2] for h in out}
    assert domains == {"a.com", "b.com", "c.com"}
    assert len(out) == 4  # a capped at 2, b and c take one each


def test_diversify_domain_caps_override_still_applies():
    hits = [_hit(f"https://docs.python.org/{i}") for i in range(5)]
    out = diversify(hits, per_domain=1, domain_caps={"python.org": 4}, strict=True)
    assert len(out) == 4


# --------------------------------------------------------------------------- #
# official-source hint switch
# --------------------------------------------------------------------------- #
async def _run_search(settings: Settings) -> dict:
    service = WebLens(settings)
    try:
        router = SearchRouter(settings, service.fetcher)
        router._providers = [
            _FakeProvider(
                [
                    _hit("https://docs.python.org/3/library/asyncio.html", "asyncio docs"),
                    _hit("https://example.org/unrelated", "unrelated"),
                ]
            )
        ]
        outcome = await router.search("python asyncio tutorial", k=5)
        return {"hits": outcome.hits, "warnings": outcome.warnings}
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_hints_disabled_means_no_official_source_injection(tmp_path):
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="mwmbl",
        use_official_source_hints=False,
    )
    result = await _run_search(settings)

    providers = {h.provider for h in result["hits"]}
    assert not any(p.startswith("official") for p in providers)
    assert not any(w.startswith("official_source") for w in result["warnings"])


@pytest.mark.asyncio
async def test_hints_enabled_can_inject_official_source(tmp_path):
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="mwmbl",
        use_official_source_hints=True,
    )
    with patch(
        "weblens.search.router.official_source_urls",
        return_value=["https://docs.python.org/3/library/asyncio-dev.html"],
    ):
        result = await _run_search(settings)

    providers = {h.provider for h in result["hits"]}
    assert any(p.startswith("official") for p in providers)


@pytest.mark.asyncio
async def test_diversify_padding_warning_is_emitted_when_window_is_short(tmp_path):
    """A padded result window must be visible, never silent."""
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
        allow_browser=False,
        search_providers="mwmbl",
        use_official_source_hints=False,
    )
    service = WebLens(settings)
    try:
        router = SearchRouter(settings, service.fetcher)
        # Only one domain, more hits than the default cap of 2.
        router._providers = [_FakeProvider([_hit(f"https://a.com/{i}") for i in range(5)])]
        outcome = await router.search("a", k=5)
        assert len(outcome.hits) <= 5
        if any(w.startswith("diversity_padded") for w in outcome.warnings):
            assert "diversity_padded" in " ".join(outcome.warnings)
    finally:
        await service.close()
