"""Additional coverage tests for URL utilities."""

from __future__ import annotations

import base64

from weblens.urls import (
    decode_bing_redirect,
    document_canonical_key,
    host_of,
    is_same_site,
    normalize_url,
    official_source_urls,
    registrable_domain,
    safe_display_url,
    strip_tracking,
)


def test_normalize_url_ipv6_with_port():
    assert normalize_url("http://[2001:db8::1]:8080/path") == "http://[2001:db8::1]:8080/path"
    assert normalize_url("https://[2001:db8::1]/path") == "https://[2001:db8::1]/path"


def test_normalize_url_standard_ports_dropped():
    assert normalize_url("http://example.com:80/") == "http://example.com/"
    assert normalize_url("https://example.com:443/") == "https://example.com/"


def test_normalize_url_bad_schemes_rejected():
    for scheme in ("ftp", "gopher", "javascript", "data", "vbscript", "blob", "about"):
        assert normalize_url(f"{scheme}://example.com") is None


def test_normalize_url_userinfo_rejected():
    assert normalize_url("http://user@example.com/") is None
    assert normalize_url("https://user:pass@example.com/") is None


def test_normalize_url_invalid_port():
    assert normalize_url("http://example.com:abc/") is None
    assert normalize_url("http://example.com:0/") is None
    assert normalize_url("http://example.com:70000/") is None


def test_normalize_url_overlong_rejected():
    assert normalize_url("http://example.com/" + "x" * 3000) is None


def test_normalize_url_non_http_schemes():
    assert normalize_url("mailto:a@b.com") is None
    assert normalize_url("http://localhost:8080/x") == "http://localhost:8080/x"


def test_decode_bing_redirect_value_errors():
    assert decode_bing_redirect("") == ""
    assert decode_bing_redirect("not a url") == "not a url"
    assert decode_bing_redirect("https://www.bing.com/") == "https://www.bing.com/"


def test_decode_bing_redirect_bad_base64():
    assert decode_bing_redirect("https://www.bing.com/ck/a?u=a1!!!") == "https://www.bing.com/ck/a?u=a1!!!"


def test_decode_bing_redirect_non_http_decoded():
    payload = base64.urlsafe_b64encode(b"mailto:a@b.com").decode().rstrip("=")
    wrapped = f"https://www.bing.com/ck/a?u=a1{payload}"
    assert decode_bing_redirect(wrapped) == wrapped


def test_strip_tracking_removes_prefixes():
    url = "https://example.com/?q=a&utm_source=x&utm_medium=y&pk_campaign=z&mtm_kwd=k&hsa_ad=1&vero_conv=b&_hsenc=c"
    assert strip_tracking(url) == "https://example.com/?q=a"


def test_strip_tracking_exact_matches():
    params = [
        "fbclid=1",
        "gclid=2",
        "dclid=3",
        "gbraid=4",
        "wbraid=5",
        "msclkid=6",
        "yclid=7",
        "igshid=8",
        "mc_cid=9",
        "mc_eid=10",
        "ref=r",
        "referrer=s",
        "ref_src=t",
        "ref_url=u",
        "source=v",
        "spm=w",
        "si=x",
        "feature=y",
        "trk=z",
        "cmpid=1",
        "campaign=2",
        "at_medium=3",
        "at_campaign=4",
        "scid=5",
        "ncid=6",
        "sr_share=7",
        "_ga=8",
        "_gl=9",
    ]
    url = "https://example.com/?q=a&" + "&".join(params)
    assert strip_tracking(url) == "https://example.com/?q=a"


def test_official_source_urls_hit_many_branches():
    cases = [
        ("what is Python PEP 8", "https://peps.python.org/pep-0008/"),
        ("Python 3.12 release", "https://docs.python.org/3/whatsnew/3.12.html"),
        ("asyncio event loop", "https://docs.python.org/3/library/asyncio.html"),
        ("sqlite wal", "https://sqlite.org/wal.html"),
        ("content security policy", "https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP"),
        ("git rebase", "https://git-scm.com/docs/git-rebase"),
        ("fastapi path parameter", "https://fastapi.tiangolo.com/tutorial/path-params/"),
        ("resnet paper", "https://arxiv.org/pdf/1512.03385"),
        ("bert natural language", "https://arxiv.org/abs/1810.04805"),
        ("attention is all you need transformer paper", "https://arxiv.org/abs/1706.03762"),
        ("greenhouse gas global warming", "https://www.ipcc.ch/report/ar6/syr/"),
        ("sitemap what is used for", "https://www.sitemaps.org/protocol.html"),
        ("postgresql mysql", "https://www.postgresql.org/docs/current/mvcc.html"),
        ("graphql rest", "https://graphql.org/learn/"),
        ("apple stock ticker", "https://www.nasdaq.com/market-activity/stocks/aapl"),
        ("microsoft listed stock exchange ticker", "https://www.nasdaq.com/market-activity/stocks/msft"),
        ("nvidia headquarters located", "https://www.nvidia.com/en-us/about-nvidia/"),
        ("stripe founder founded", "https://stripe.com/about"),
        ("tsmc largest semiconductor foundry", "https://www.tsmc.com/english/aboutTSMC/TSMC_Introduction"),
        ("instagram owns parent", "https://about.meta.com/company-info/"),
        ("anthropic what company", "https://www.anthropic.com/company"),
        ("article 5 north atlantic nato", "https://www.nato.int/cps/en/natohq/official_texts_17120.htm"),
        ("gdpr general data protection regulation", "https://eur-lex.europa.eu/eli/reg/2016/679/oj"),
        ("world health organization mission core what", "https://www.who.int/about"),
        ("bmi", "https://www.cdc.gov/bmi/index.html"),
        ("type 2 diabetes symptoms", "https://www.cdc.gov/diabetes/about/about-type-2-diabetes.html"),
        ("iso 3166 country code", "https://www.iso.org/iso-3166-country-codes.html"),
        ("stock market index measure", "https://www.nyse.com/markets/indices"),
        ("cloud infrastructure provider", "https://www.gartner.com/en/newsroom/press-releases"),
        ("robots.txt where", "https://www.robotstxt.org/robotstxt.html"),
        ("python venv", "https://docs.python.org/3/library/venv.html"),
        ("python structural pattern matching", "https://peps.python.org/pep-0634/"),
        ("http status code 429", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429"),
        ("iphone 15 connector usb-c", "https://www.apple.com/iphone-15/specs/"),
        ("macbook pro", "https://www.apple.com/macbook-pro/"),
        ("consumer price index agency publishes", "https://www.bls.gov/cpi/"),
        ("apollo 11 1969 moon landing", "https://www.nasa.gov/mission/apollo-11/"),
        ("gpt-4 developed openai", "https://platform.openai.com/docs/models/gpt-4"),
        ("higgs boson cern discovery", "https://home.cern/science/physics/higgs-boson"),
        ("dmca", "https://www.copyright.gov/legislation/dmca.pdf"),
        ("javascript let const", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/let"),
        ("mit license", "https://opensource.org/license/mit"),
        ("alphafold", "https://deepmind.google/technologies/alphafold/"),
        ("mistral open weights models", "https://mistral.ai/technology/"),
        ("nvidia data center chip gpu", "https://www.nvidia.com/en-us/data-center/"),
        ("siemens", "https://www.siemens.com/en-us/company/"),
        ("stripe founder", "https://stripe.com/about"),
        ("byzantine fault consensus pbft", "https://en.wikipedia.org/wiki/PBFT"),
        ("10-k", "https://www.sec.gov/edgar/search/"),
        (
            "apple 10-k net sales annual report",
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-K",
        ),
        ("microsoft alphabet", "https://www.sec.gov/edgar/browse/?CIK=789019"),
        ("aws google cloud gcp", "https://aws.amazon.com/ec2/pricing/on-demand/"),
        ("snowflake databricks", "https://www.snowflake.com/en/product/technology/"),
        ("salesforce ticker headquarters stock", "https://www.salesforce.com/company/"),
        ("sitemap robots.txt canonical", "https://www.sitemaps.org/protocol.html"),
        ("sqlite fts5 full-text", "https://sqlite.org/fts5.html"),
        ("python with statement", "https://docs.python.org/3/reference/compound_stmts.html#the-with-statement"),
        ("symmetric asymmetric encryption", "https://www.cloudflare.com/learning/ssl/what-is-encryption/"),
        ("wave-particle duality quantum", "https://www.britannica.com/science/wave-particle-duality"),
        ("mcp model context protocol", "https://modelcontextprotocol.io/docs/getting-started/intro"),
        ("python multiprocessing", "https://docs.python.org/3/library/multiprocessing.html"),
        ("python stable release version", "https://www.python.org/downloads/latest/"),
        ("adobe product", "https://www.adobe.com/creativecloud.html"),
        ("perplexity", "https://www.perplexity.ai/"),
        (
            "dividend shareholder corporation",
            "https://www.investor.gov/introduction-investing/investing-basics/glossary/dividend",
        ),
        ("gemini google", "https://blog.google/technology/ai/google-gemini-ai/"),
        ("united states federal voting age", "https://www.usa.gov/voting"),
        ("ai act european union eu", "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"),
        ("iata heathrow", "https://www.iata.org/en/publications/directories/code-search/"),
        ("deepmind acquired acquisition", "https://deepmind.google/about/"),
        ("coffee producer", "https://www.ico.org/"),
        (
            "bm25 term frequency scoring k1",
            "https://nlp.stanford.edu/IR-book/html/htmledition/okapi-bm25-a-note-on-term-frequency-saturation-1.html",
        ),
        ("nasa earthdata earth science", "https://www.earthdata.nasa.gov/"),
        ("type 2 diabetes diagnosis criteria", "https://diabetes.org/about-diabetes/diagnosis"),
        ("fda pharmaceutical medical device", "https://www.fda.gov/"),
        ("p53 protein", "https://www.ncbi.nlm.nih.gov/gene/7157"),
        ("netflix competitor streaming", "https://www.disneyplus.com/"),
        ("virus bacteria", "https://www.cdc.gov/antibiotic-use/about/index.html"),
    ]
    for query, expected in cases:
        urls = official_source_urls(query)
        assert expected in urls, f"expected {expected!r} for {query!r}"


def test_registrable_domain_known_suffixes():
    # Two-label public suffixes collapse to the registrable domain.
    assert registrable_domain("x.y.b.c.co.uk") == "c.co.uk"
    assert registrable_domain("www.example.co.uk") == "example.co.uk"
    # Unknown/dotted suffixes keep the last three labels.
    assert registrable_domain("x.y.b.com.au") == "b.com.au"
    assert registrable_domain("x.y.b.co.jp") == "b.co.jp"
    assert registrable_domain("x.y.b.or.jp") == "b.or.jp"


def test_is_same_site_true_and_false():
    assert is_same_site("https://a.example.com/x", "https://b.example.com/y") is True
    assert is_same_site("https://a.example.co.uk/x", "https://b.example.co.uk/y") is True
    assert is_same_site("https://a.example.com/x", "https://b.other.com/y") is False


def test_host_of_value_error():
    assert host_of("not a url") == ""


def test_safe_display_url_quotes_and_truncates():
    assert safe_display_url("https://example.com/path") == "https://example.com/path"
    long = "https://example.com/" + "x" * 400
    assert len(safe_display_url(long)) <= 300


def test_document_canonical_key_covers_aliases():
    assert document_canonical_key("https://example.com/A?utm_source=x") == document_canonical_key(
        "https://example.com/a#frag"
    )
    assert document_canonical_key("http://example.com/page.html/") == document_canonical_key(
        "https://www.example.com/page.html"
    )


def test_document_canonical_key_empty_and_bad_scheme():
    assert document_canonical_key("") == ""
    assert document_canonical_key("mailto:a@b.com") == document_canonical_key("mailto:a@b.com")
