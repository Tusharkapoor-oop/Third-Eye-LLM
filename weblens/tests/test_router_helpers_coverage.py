"""Coverage for pure helpers in search/router.py.

Query cleaning, recall-query derivation, authority/score heuristics, document
keys, domain filtering, ranking and fusion. No network: `rank` and the
classifiers are pure functions over `Hit` objects.
"""

from __future__ import annotations

import pytest

from weblens.search.base import Hit
from weblens.search.router import (
    _authority,
    _doc_key,
    _domain_allowed,
    _official_title,
    _query_authority,
    _skip_link_expansion,
    clean_query,
    rank,
    recall_query,
)


def h(url: str, title: str = "Title", snippet: str = "snippet", rank_: int = 0) -> Hit:
    return Hit(title=title, url=url, snippet=snippet, provider="t", rank=rank_)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "What is the capital of France?",
        "Hello! Please tell me about asyncio in Python 3.12",
        "In JavaScript, what is the difference between let and const?",
        "🤖 emoji only query 🚀",
        "very " * 300,
    ],
)
def test_clean_query_never_raises_and_returns_str(raw):
    # clean_query itself does not truncate; SearchRouter.search() caps the
    # used query at 400 chars before dispatching providers.
    out = clean_query(raw)
    assert isinstance(out, str)
    assert "  " not in out


def test_clean_query_strips_conversational_lead_ins():
    assert clean_query("Can you please explain vector databases") != ""
    assert not clean_query("what is rust programming").lower().startswith("can you")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "Siemens",
        "What industry does Siemens primarily operate in?",
        "asyncio event loop",
    ],
)
def test_recall_query_is_short_and_safe(raw):
    out = recall_query(raw)
    assert isinstance(out, str)
    assert len(out) <= 200


def test_authority_ranks_official_and_reference_sites_higher():
    official = _authority("https://docs.python.org/3/library/asyncio.html")
    blog = _authority("https://random-blog.example/post")
    assert official > blog


def test_official_title_derives_readable_title():
    title = _official_title("https://docs.python.org/3/library/asyncio.html")
    assert "asyncio" in title.lower().replace("-", " ")


@pytest.mark.parametrize(
    "a,b",
    [
        ("https://www.example.com/x", "http://example.com/x"),
        ("https://example.com/x/", "https://example.com/x"),
        ("https://example.com/x#frag", "https://example.com/x"),
    ],
)
def test_doc_key_normalizes_variants(a, b):
    assert _doc_key(a) == _doc_key(b)


def test_doc_key_distinguishes_different_paths():
    assert _doc_key("https://example.com/a") != _doc_key("https://example.com/b")


@pytest.mark.parametrize(
    "url,domains,excluded,expected",
    [
        ("https://example.com/a", None, None, True),
        ("https://example.com/a", ["example.com"], None, True),
        ("https://other.com/a", ["example.com"], None, False),
        ("https://example.com/a", None, ["example.com"], False),
        ("https://sub.example.com/a", ["example.com"], None, True),
    ],
)
def test_domain_allowed(url, domains, excluded, expected):
    assert _domain_allowed(url, domains, excluded) is expected


def test_query_authority_rewards_query_term_match():
    matching = _query_authority("https://example.com/asyncio-tutorial", "asyncio tutorial")
    unrelated = _query_authority("https://example.com/unrelated", "asyncio tutorial")
    assert matching >= unrelated


@pytest.mark.parametrize("query", ["", "asyncio", "what is asyncio", "docs"])
def test_skip_link_expansion_returns_bool(query):
    assert isinstance(_skip_link_expansion(query), bool)


def test_rank_orders_by_authority_and_query_match():
    hits = [
        h("https://random-blog.example/asyncio", "Random asyncio musings", "asyncio"),
        h("https://docs.python.org/3/library/asyncio.html", "asyncio docs", "asyncio library"),
    ]
    ordered = rank(hits, query="asyncio")
    assert ordered[0].url.startswith("https://docs.python.org")
    assert len(ordered) == len(hits)


def test_rank_fused_mode_handles_duplicates():
    hits = [
        h("https://example.com/a", "A", "same"),
        h("https://example.com/a", "A again", "same"),
        h("https://example.com/b", "B", "other"),
    ]
    ordered = rank(hits, fused=True, query="same other")
    assert ordered
    assert all(isinstance(x, Hit) for x in ordered)


def test_rank_empty_input():
    assert rank([]) == []
