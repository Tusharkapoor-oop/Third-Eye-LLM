from __future__ import annotations

import base64

import pytest

from weblens.urls import (
    decode_bing_redirect,
    host_of,
    is_same_site,
    normalize_url,
    registrable_domain,
    strip_tracking,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("HTTPS://Example.COM/Path/?utm_source=x&b=2&a=1#frag", "https://example.com/Path?a=1&b=2"),
        ("http://example.com:80/", "http://example.com/"),
        ("https://example.com:443/a//b/", "https://example.com/a/b"),
        ("http://example.com/a%20b", "http://example.com/a%20b"),
    ],
)
def test_normalize_url_canonicalizes(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:text/html,hi",
        "ftp://example.com/x",
        "http://user:pass@example.com/",
        "http://intranet/",
        "http://example.com:0/",
        "http://example.com:99999/",
        "http://example.com/" + "a" * 3000,
    ],
)
def test_normalize_url_rejects_unsafe_or_unusable(raw):
    assert normalize_url(raw) is None


def test_normalize_url_allows_localhost_and_ipv6():
    assert normalize_url("http://localhost:8080/x") == "http://localhost:8080/x"
    assert normalize_url("https://[2606:4700::1111]/x") == "https://[2606:4700::1111]/x"


def test_normalize_url_relative_base():
    assert normalize_url("../b?utm_medium=x", "https://example.com/a/c") == "https://example.com/b"


def test_strip_tracking_keeps_real_parameters():
    assert strip_tracking("https://e.com/?q=python&utm_source=x&gclid=y") == "https://e.com/?q=python"


def test_decode_bing_redirect_valid_and_invalid():
    target = "https://example.com/page"
    payload = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    wrapped = f"https://www.bing.com/ck/a?u=a1{payload}"
    assert decode_bing_redirect(wrapped) == target
    assert decode_bing_redirect("https://www.bing.com/ck/a?u=nope") == "https://www.bing.com/ck/a?u=nope"
    assert decode_bing_redirect("https://example.com/x") == "https://example.com/x"


def test_registrable_domain_common_suffixes():
    assert registrable_domain("docs.python.org") == "python.org"
    assert registrable_domain("news.bbc.co.uk") == "bbc.co.uk"
    assert registrable_domain("localhost") == "localhost"


def test_is_same_site_and_host_of():
    assert is_same_site("https://a.example.com/x", "https://b.example.co.uk/y") is False
    assert is_same_site("https://a.example.com/x", "https://b.example.com/y") is True
    assert host_of("https://Example.COM/x") == "example.com"
    assert host_of("not a url") == ""
