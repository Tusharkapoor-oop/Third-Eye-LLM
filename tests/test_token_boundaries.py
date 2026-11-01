"""
Token Budget Boundary Testing Suite
Verifies output never exceeds token budgets under adversarial input.
R1 Requirement: Schema < 1000 tokens, Search <= 600, Extract <= 1500, Research <= 2000.
"""
from __future__ import annotations

import json

import pytest
import tiktoken

from src.engine.config import CONFIG
from src.engine.crawl.crawler import WebsiteCrawler
from src.engine.extract.extractor import DocumentExtractor
from src.engine.research.deep_research import DeepResearchEngine
from src.engine.search.aggregator import SearchAggregator
from src.server.token_counter import measure_tool_schema_tokens

TOKENIZER = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(TOKENIZER.encode(text))


def test_schema_tokens_under_1000() -> None:
    report = measure_tool_schema_tokens()
    assert report["total_o200k"] <= 1000, f"Schema too large: {report['total_o200k']} tokens (o200k)"
    assert report["total_cl100k"] <= 1000, f"Schema too large: {report['total_cl100k']} tokens (cl100k)"
    print(f"\nSchema tokens: o200k={report['total_o200k']}, cl100k={report['total_cl100k']}")


SEARCH_QUERIES = [
    "capital of France",
    "speed of light vacuum",
    "Python asyncio gather return_exceptions parameter",
    "PEP 703 free threading optional GIL Python 3.13",
    "HTTP/3 QUIC underlying transport protocol",
    "",
    "a" * 500,
    "日本語 で 検索",
    "🚀 rocket emoji query 🔥",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", SEARCH_QUERIES)
async def test_search_token_budget(query: str) -> None:
    aggregator = SearchAggregator()
    resp = await aggregator.search(query, count=10, max_tokens=CONFIG.default_search_tokens)

    response_dict = resp.to_dict()
    response_json = json.dumps(response_dict, separators=(",", ":"))
    total_tokens = count_tokens(response_json)

    assert total_tokens <= CONFIG.default_search_tokens + 50, \
        f"Search exceeded token budget: {total_tokens} tokens for query: {query[:50]}..."
    assert resp.status in ("success", "no_reliable_result")

    for r in resp.results:
        assert r.url.startswith("http"), f"Invalid URL: {r.url}"

    print(f"\nSearch '{query[:40]:<40}': status={resp.status}, results={len(resp.results)}, tokens={total_tokens}")


@pytest.mark.asyncio
async def test_search_max_count_respected() -> None:
    aggregator = SearchAggregator()
    resp = await aggregator.search("Python programming", count=10, max_tokens=600)
    assert len(resp.results) <= 10


EXTRACT_URLS = [
    "https://www.python.org/about/",
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("url", EXTRACT_URLS)
async def test_extract_token_budget(url: str) -> None:
    extractor = DocumentExtractor()
    doc = await extractor.extract_url(
        url, query="Python programming language", mode="passages",
        max_tokens=CONFIG.default_extract_tokens
    )

    response_dict = doc.to_dict()
    response_json = json.dumps(response_dict, separators=(",", ":"))
    total_tokens = count_tokens(response_json)

    assert total_tokens <= CONFIG.default_extract_tokens + 100, \
        f"Extract exceeded token budget: {total_tokens} tokens for {url}"
    assert doc.status in ("success", "blocked", "empty_content", "fetch_failed")

    if doc.status == "success":
        assert len(doc.passages) > 0
        for p in doc.passages:
            assert p.char_start >= 0
            assert p.char_end > p.char_start
            assert p.token_count > 0

    print(f"\nExtract {url}: status={doc.status}, passages={len(doc.passages)}, tokens={total_tokens}")


@pytest.mark.asyncio
async def test_extract_full_mode_budget() -> None:
    extractor = DocumentExtractor()
    doc = await extractor.extract_url(
        "https://www.python.org/about/",
        query=None, mode="full", max_tokens=CONFIG.default_extract_tokens
    )

    if doc.status == "success" and doc.full_text:
        full_tokens = count_tokens(doc.full_text)
        assert full_tokens <= CONFIG.default_extract_tokens * 2 + 50, \
            f"Full text exceeded 2x budget: {full_tokens} tokens"
        print(f"\nFull mode tokens: {full_tokens} (budget 2x={CONFIG.default_extract_tokens * 2})")


RESEARCH_QUESTIONS = [
    "What is the capital of France?",
    "How does Python asyncio work?",
    "What is PEP 703?",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("question", RESEARCH_QUESTIONS)
async def test_deep_research_token_budget(question: str) -> None:
    researcher = DeepResearchEngine()
    report = await researcher.research(
        question=question, max_searches=3, max_pages=5,
        max_tokens=CONFIG.default_research_tokens
    )

    response_dict = report.to_dict()
    response_json = json.dumps(response_dict, separators=(",", ":"))
    total_tokens = count_tokens(response_json)

    assert total_tokens <= CONFIG.default_research_tokens + 200, \
        f"Research exceeded token budget: {total_tokens} tokens for: {question}"
    assert report.status in ("sufficient_evidence", "partial_evidence",
                             "conflicting_sources", "no_reliable_result")

    print(f"\nResearch '{question[:40]:<40}': status={report.status}, facts={len(report.facts)}, tokens={total_tokens}")


@pytest.mark.asyncio
async def test_crawl_tokens_per_page() -> None:
    crawler = WebsiteCrawler()
    res = await crawler.crawl(
        "https://www.python.org/about/",
        max_depth=1, max_pages=3, max_tokens_per_page=800
    )

    assert res["status"] == "completed"
    for page in res["pages"]:
        assert page["tokens_used"] <= 800 + 50, \
            f"Crawl page exceeded per-page budget: {page['tokens_used']} tokens"
    print(f"\nCrawl: pages={res['total_pages_crawled']}, skipped={res['skipped_urls']}")
