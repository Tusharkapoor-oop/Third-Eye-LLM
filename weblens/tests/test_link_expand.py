from __future__ import annotations

import pytest

from weblens.search.link_expand import (
    _prefix_match,
    _strong_prefix_match,
    expand_official_links,
    extract_same_site_links,
)
from weblens.search.router import _skip_link_expansion


def test_prefix_matching_rejects_generic_three_letter_stems():
    assert not _prefix_match({"protein"}, {"programs"})
    assert _prefix_match({"taskgroup"}, {"task"})
    assert _strong_prefix_match({"fts5"}, {"fts3"})
    assert not _strong_prefix_match({"alphafold"}, {"alphaearth"})


def test_same_site_links_prefer_specific_related_pages():
    html = """
    <a href="/3/library/asyncio-task.html">TaskGroup</a>
    <a href="/3/library/asyncio-api-index.html">High-level API Index</a>
    <a href="/3/library/asyncio-dev.html">Developing with asyncio</a>
    <a href="/3/library/json.html">json</a>
    <a href="/3/whatsnew/3.12.html">What's New</a>
    <a href="https://example.com/elsewhere">elsewhere</a>
    """
    links = extract_same_site_links(
        html,
        "https://docs.python.org/3/library/asyncio.html",
        "How does asyncio.gather differ from asyncio.TaskGroup in Python 3.11+?",
        [],
        limit=3,
    )
    urls = [url for url, _ in links]
    assert urls[0].endswith("/3/library/asyncio-task.html")
    assert all("json" not in url for url in urls)
    assert all("3.12" not in url for url in urls)


def test_versioned_query_does_not_expand_into_another_release():
    html = """
    <a href="/3/whatsnew/3.13.html">Python 3.13 changes</a>
    <a href="/3/library/asyncio-task.html">TaskGroup</a>
    """
    links = extract_same_site_links(
        html,
        "https://docs.python.org/3/whatsnew/3.14.html",
        "What changed in Python 3.14 for asyncio?",
        [],
        limit=3,
    )
    urls = [url for url, _ in links]
    assert all("3.13" not in url for url in urls)
    assert any("asyncio-task" in url for url in urls)


class FakeFetcher:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages

    async def fetch(self, url: str, **kwargs):
        class Response:
            text = self.pages.get(url, "")

        return Response()


@pytest.mark.asyncio
async def test_expansion_ranks_candidates_across_all_fetched_pages():
    first = "https://example.com/docs/a.html"
    second = "https://example.com/docs/b.html"
    fetcher = FakeFetcher(
        {
            first: '<a href="/docs/task.html">task</a>',
            second: '<a href="/docs/deep-task.html">deep task</a>',
        }
    )
    out = await expand_official_links(
        fetcher,
        [first, second],
        "deep task",
        [],
        max_pages=2,
        max_links=2,
    )
    assert out
    assert out[0][0] == "https://example.com/docs/deep-task.html"


@pytest.mark.asyncio
async def test_expansion_can_fill_a_full_result_window():
    html = """
    <a href="/docs/task-one.html">task one</a>
    <a href="/docs/task-two.html">task two</a>
    <a href="/docs/task-three.html">task three</a>
    <a href="/docs/task-four.html">task four</a>
    <a href="/docs/task-five.html">task five</a>
    """
    fetcher = FakeFetcher({"https://example.com/docs/index.html": html})
    out = await expand_official_links(
        fetcher,
        ["https://example.com/docs/index.html"],
        "task",
        [],
        max_pages=1,
        max_links=4,
    )
    assert len(out) == 4


def test_freshness_queries_skip_link_expansion():
    assert _skip_link_expansion("What is the current stable release version of Python 3?")
    assert _skip_link_expansion("What is the latest version of Node.js?")
    assert not _skip_link_expansion("What is the role of the p53 protein in cancer?")
