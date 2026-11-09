"""Blank and chrome-only HTML must not crash extraction."""

from __future__ import annotations

from weblens.extract.html import (
    _clean_text,
    _fallback_extract,
    age_days,
    extract_html,
    extract_meta,
    heading_of,
    normalize_date,
)


def test_blank_html_and_bullet_boilerplate_are_contained():
    assert normalize_date(None) is None
    assert _fallback_extract("") == ("", "")
    assert extract_meta("") == {"title": None, "author": None, "published": None, "sitename": None}

    doc = extract_html("", "https://example.com")
    assert doc.text == ""
    assert "low_content" in doc.warnings

    assert _clean_text("\u2022 Skip to content\nHello") == "Hello"
    assert heading_of("no heading here", 0) is None
    assert age_days(None) is None
