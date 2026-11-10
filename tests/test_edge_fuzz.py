"""
Edge Case & Fuzz Testing Suite
Verifies no crashes on weird, malicious, or unexpected input.
"""
from __future__ import annotations

import pytest

from src.engine.extract.extractor import DocumentExtractor
from src.engine.search.aggregator import SearchAggregator, normalize_url
from src.engine.security import validate_url_security

# ---------------------------------------------------------------------------
# URL normalization edge cases
# ---------------------------------------------------------------------------

NORMALIZATION_CASES = [
    # (input, expected_substring_or_none)
    ("https://example.com/blog/article/?utm_source=twitter&utm_medium=social#heading-2",
     "https://example.com/blog/article"),
    ("https://docs.python.org/3/library/asyncio.html?fbclid=12345",
     "https://docs.python.org/3/library/asyncio.html"),
    # Only scheme and host are case-insensitive (RFC 3986 §6.2.2.1); a path is
    # case-sensitive, so /Path and /path are different resources.
    ("https://Example.COM/Path/", "https://example.com/Path"),
    ("https://example.com/path//double///slash", "https://example.com/path"),
    ("https://example.com/path/", "https://example.com/path"),
]


@pytest.mark.parametrize("raw_url, expected", NORMALIZATION_CASES)
def test_url_normalization_edge_cases(raw_url: str, expected: str) -> None:
    clean = normalize_url(raw_url)
    assert expected in clean, f"Normalization failed: {raw_url} -> {clean}, expected {expected}"


# ---------------------------------------------------------------------------
# Search edge cases
# ---------------------------------------------------------------------------

SEARCH_EDGE_CASES = [
    ("", "empty query"),
    (" ", "whitespace query"),
    ("a", "single char"),
    ("a" * 500, "500 char query"),
    ("日本語 で 検索", "Japanese query"),
    ("🚀 rocket 🔥 fire", "emoji query"),
    ("SELECT * FROM users; DROP TABLE users; --", "SQL injection string"),
    ("<script>alert('xss')</script>", "XSS string"),
    ("query\nwith\nnewlines", "newlines in query"),
    ("query\twith\ttabs", "tabs in query"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query, description", SEARCH_EDGE_CASES)
async def test_search_edge_cases(query: str, description: str) -> None:
    aggregator = SearchAggregator()
    try:
        resp = await aggregator.search(query, count=3, max_tokens=300)
        assert resp.status in ("success", "no_reliable_result")
        print(f"\nSearch edge '{description}': status={resp.status}, results={len(resp.results)}")
    except Exception as e:
        # Some edge cases may legitimately error, but should not crash hard
        pytest.fail(f"Unhandled exception for {description}: {e}")


# ---------------------------------------------------------------------------
# Extract edge cases
# ---------------------------------------------------------------------------

EXTRACT_EDGE_URLS = [
    "https://example.com/",  # simple
    "https://httpbin.org/html",  # test HTML
]


@pytest.mark.asyncio
@pytest.mark.parametrize("url", EXTRACT_EDGE_URLS)
async def test_extract_edge_cases(url: str) -> None:
    extractor = DocumentExtractor()
    try:
        doc = await extractor.extract_url(url, query=None, mode="passages", max_tokens=600)
        assert doc.status in ("success", "blocked", "empty_content", "fetch_failed")
        print(f"\nExtract edge {url}: status={doc.status}, passages={len(doc.passages)}")
    except Exception as e:
        pytest.fail(f"Unhandled exception for extract {url}: {e}")


# ---------------------------------------------------------------------------
# Very long URL
# ---------------------------------------------------------------------------

def test_very_long_url() -> None:
    long_url = "https://example.com/" + "a" * 5000
    is_safe, reason, _ = __import__("src.engine.security", fromlist=["validate_url_security"]).validate_url_security(long_url)
    # Should either be safe (long but valid) or rejected for length
    assert isinstance(is_safe, bool)
    print(f"\nVery long URL (5000 chars): safe={is_safe}, reason={reason[:50]}")


# ---------------------------------------------------------------------------
# Null bytes in URL
# ---------------------------------------------------------------------------

def test_null_byte_in_url() -> None:
    url_with_null = "http://example.com/\x00/"
    is_safe, reason, _ = validate_url_security(url_with_null)
    # Null bytes should be rejected
    assert is_safe is False, f"Null byte URL should be blocked: {url_with_null}"
