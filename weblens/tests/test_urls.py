from __future__ import annotations

import base64

import pytest

from weblens.urls import (
    decode_bing_redirect,
    host_of,
    is_same_site,
    normalize_url,
    official_source_urls,
    registrable_domain,
    strip_tracking,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("HTTPS://Example.COM/Path/?utm_source=x&b=2&a=1#frag", "https://example.com/Path/?a=1&b=2"),
        ("http://example.com:80/", "http://example.com/"),
        ("https://example.com:443/a//b/", "https://example.com/a/b/"),
        ("https://example.com/a", "https://example.com/a"),
        ("http://example.com/a%20b", "http://example.com/a%20b"),
        # Percent-encoding is preserved verbatim: decoding it corrupts
        # double-encoded inputs and can emit invalid URLs.
        ("https://example.com/x%25y", "https://example.com/x%25y"),
        ("https://example.com/a%2526b", "https://example.com/a%2526b"),
        ("https://example.com/p%25q/%20x", "https://example.com/p%25q/%20x"),
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


def test_official_source_urls_cover_high_confidence_common_topics():
    wave = official_source_urls("Is light classified as a particle or a wave in quantum mechanics?")
    assert "https://www.britannica.com/science/wave-particle-duality" in wave

    encryption = official_source_urls("What is the difference between symmetric and asymmetric encryption?")
    assert any("cloudflare.com" in url for url in encryption)
    assert "https://en.wikipedia.org/wiki/Public-key_cryptography" in encryption

    stable = official_source_urls("What is the current stable release version of Python 3?")
    assert stable[0] == "https://www.python.org/downloads/latest/"

    with_statement = official_source_urls(
        "In Python, what does the with statement guarantee when used with a context manager?"
    )
    assert any("compound_stmts.html" in url for url in with_statement)
    assert any("datamodel.html" in url for url in with_statement)


def test_official_source_urls_cover_scarce_primary_source_topics():
    ten_k = official_source_urls("What is a 10-K filing that public companies submit to the SEC?")
    assert "https://www.sec.gov/edgar/search/" in ten_k
    assert "https://www.investopedia.com/terms/1/10-k.asp" in ten_k

    resnet = official_source_urls("Which paper introduced the ResNet architecture and when was it published?")
    assert "https://arxiv.org/pdf/1512.03385" in resnet

    transformer = official_source_urls("Who are the authors of Attention Is All You Need?")
    assert any(url.endswith("-Paper.pdf") for url in transformer)

    macbook = official_source_urls("What are the specifications and battery life of the M4 MacBook Pro?")
    assert "https://www.apple.com/macbook-pro/" in macbook
    assert "https://www.apple.com/macbook-pro/specs/" in macbook

    siemens = official_source_urls("What industry does the company Siemens primarily operate in?")
    assert "https://www.siemens.com/en-us/company/about/" in siemens

    fda = official_source_urls("Which US agency regulates pharmaceutical drugs and medical devices?")
    assert "https://www.fda.gov/" in fda

    p53 = official_source_urls("What is the role of the p53 protein in cancer?")
    assert "https://www.ncbi.nlm.nih.gov/gene/7157" in p53

    netflix = official_source_urls("Which streaming services compete directly with Netflix?")
    assert "https://www.netflix.com/" in netflix
    assert "https://www.disneyplus.com/" in netflix

    microsoft = official_source_urls("On which stock exchange is Microsoft Corporation primarily listed?")
    assert "https://www.nasdaq.com/market-activity/stocks/msft" in microsoft
    assert "https://www.microsoft.com/en-us/investor" in microsoft

    index = official_source_urls("What does a stock market index measure?")
    assert "https://www.investopedia.com/terms/m/marketindex.asp" in index

    pep = official_source_urls("What is Python PEP 703 and how does it make the GIL optional?")
    assert "https://peps.python.org/pep-0703/" in pep
    assert "https://peps.python.org/pep-0008/" in official_source_urls("What is PEP 8?")
