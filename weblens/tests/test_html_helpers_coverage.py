"""Coverage for the pure helpers in extract/html.py.

These are deterministic text/DOM utilities with no network access: boilerplate
stripping, JS-shell detection, the trafilatura fallback path, meta extraction,
plain-text extraction, date normalisation, and heading lookup.
"""

from __future__ import annotations

import pytest

from weblens.extract.html import (
    BOILERPLATE,
    _clean_text,
    _fallback_extract,
    _is_js_shell,
    age_days,
    extract_html,
    extract_meta,
    extract_plain,
    heading_of,
    normalize_date,
)

ARTICLE_HTML = """
<html><head>
  <title>Understanding Asyncio</title>
  <meta name="description" content="A practical guide to asyncio.">
  <meta property="article:published_time" content="2025-03-04T10:00:00Z">
  <meta name="author" content="Jane Doe">
</head><body>
  <nav>Home | About | Contact</nav>
  <main>
    <h1>Understanding Asyncio</h1>
    <p>Asyncio is a library for writing concurrent code using async/await syntax.</p>
    <p>The event loop schedules coroutines and dispatches callbacks efficiently.</p>
    <h2>Running tasks</h2>
    <p>Use asyncio.run() as the entry point for your program.</p>
    <pre><code>asyncio.run(main())</code></pre>
  </main>
  <footer>Copyright 2025</footer>
</body></html>
"""


def test_clean_text_strips_boilerplate_lines():
    boilerplate = next(iter(BOILERPLATE))
    raw = f"Real content here.\n{boilerplate}\nMore real content."
    cleaned = _clean_text(raw)
    assert "Real content here." in cleaned
    assert "More real content." in cleaned
    assert boilerplate not in cleaned.lower()


def test_clean_text_preserves_code_fences_and_drops_line_numbers():
    raw = "Intro text.\n```\ncode line\n```\n1234\nOutro text."
    cleaned = _clean_text(raw)
    assert "```" in cleaned
    assert "code line" in cleaned
    assert "\n1234\n" not in cleaned
    assert "Outro text." in cleaned


@pytest.mark.parametrize(
    "html,expected",
    [
        ('<html><body><div id="root"></div><noscript>Enable JavaScript</noscript></body></html>', True),
        ("<html><body><p>Please enable JavaScript to continue.</p></body></html>", True),
        ("<html><body><p>" + ("Real content. " * 200) + '</p><div id="root"></div></body></html>', False),
        ("<html><body><p>Short but genuine article text.</p></body></html>", False),
    ],
)
def test_is_js_shell_detection(html, expected):
    assert _is_js_shell(html) is expected


def test_fallback_extract_returns_title_and_body():
    title, text = _fallback_extract(ARTICLE_HTML)
    assert "Asyncio" in title
    assert "concurrent code" in text
    # Scripts/nav/footer are stripped from the fallback body.
    assert "Copyright" not in text


def test_fallback_extract_handles_unparseable_input():
    assert _fallback_extract("") == ("", "")


def test_extract_meta_reads_standard_tags():
    meta = extract_meta(ARTICLE_HTML)
    assert meta["title"] == "Understanding Asyncio"
    assert meta["author"] == "Jane Doe"
    assert meta["published"].startswith("2025-03-04")
    # The schema is fixed; unknown meta names do not invent keys.
    assert set(meta) == {"title", "author", "published", "sitename"}


def test_extract_html_produces_text_and_metadata():
    doc = extract_html(ARTICLE_HTML, "https://example.com/asyncio")
    assert "Asyncio" in doc.title
    assert "concurrent code" in doc.text
    assert doc.url == "https://example.com/asyncio"
    assert isinstance(doc.links, list)


def test_extract_html_can_include_links():
    html = '<html><body><main><p>Body text for the page.</p><a href="/x">X</a></main></body></html>'
    doc = extract_html(html, "https://example.com/page", include_links=True)
    assert ("https://example.com/x", "X") in doc.links


def test_extract_plain_normalizes_whitespace():
    doc = extract_plain("Line one.\r\n\r\n\r\n\r\nLine two.", "https://example.com/p", "Title")
    assert "Line one." in doc.text
    assert "Line two." in doc.text
    assert doc.title == "Title"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2025-03-04", "2025-03-04"),
        ("2025-03-04T10:00:00Z", "2025-03-04"),
        ("not a date", None),
        (None, None),
        ("", None),
    ],
)
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.parametrize(
    "iso,ok",
    [("2025-01-01", True), ("2024-01-01", True), ("bogus", False), ("", False)],
)
def test_age_days(iso, ok):
    got = age_days(iso)
    if ok:
        assert isinstance(got, int) and got >= 0
    else:
        assert got is None


def test_heading_of_returns_nearest_heading():
    text = "# Title\n\nIntro paragraph.\n\n## Section\n\nBody under section."
    idx = text.index("Body under section.")
    heading = heading_of(text, idx)
    assert heading is not None
    assert "Section" in heading or "Title" in heading


def test_heading_of_returns_none_at_document_start():
    assert heading_of("Plain paragraph with no headings.", 0) is None
