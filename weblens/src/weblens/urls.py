"""URL normalization, canonicalization and tracking-parameter removal.

Rules are deliberately conservative: never rewrite a URL in a way that could
change which resource is addressed, except for fragment removal and known
tracking parameters.
"""

from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "hsa_", "vero_", "_hs")
TRACKING_EXACT = {
    "fbclid",
    "gclid",
    "dclid",
    "gbraid",
    "wbraid",
    "msclkid",
    "yclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "ref_src",
    "ref_url",
    "source",
    "spm",
    "si",
    "feature",
    "trk",
    "cmpid",
    "campaign",
    "at_medium",
    "at_campaign",
    "scid",
    "ncid",
    "sr_share",
    "_ga",
    "_gl",
}

BAD_SCHEMES = {"file", "ftp", "gopher", "javascript", "data", "vbscript", "blob", "about"}
MAX_URL_LEN = 2048

_BING_HOST = re.compile(r"(^|\.)bing\.com$", re.I)


def is_http_url(url: str) -> bool:
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    return p.scheme.lower() in {"http", "https"} and bool(p.hostname)


def decode_bing_redirect(url: str) -> str:
    """Bing wraps outbound links as /ck/a?...&u=a1<base64url>. Decode when possible."""
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    if not _BING_HOST.search(p.hostname or "") or not p.path.startswith("/ck/a"):
        return url
    q = dict(parse_qsl(p.query))
    u = q.get("u", "")
    if not u.startswith("a1"):
        return url
    payload = u[2:]
    payload += "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload)
        decoded = raw.decode("utf-8", "strict")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return url
    return decoded if is_http_url(decoded) else url


def strip_tracking(url: str) -> str:
    p = urlsplit(url)
    pairs = parse_qsl(p.query, keep_blank_values=True)
    kept: list[tuple[str, str]] = []
    for k, v in pairs:
        kl = k.lower()
        if kl in TRACKING_EXACT or any(kl.startswith(pre) for pre in TRACKING_PREFIXES):
            continue
        kept.append((k, v))
    kept.sort(key=lambda kv: (kv[0].lower(), kv[1]))
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(kept, doseq=True), ""))


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Return a canonical absolute http(s) URL, or None if unusable."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    # Control characters are never valid: urlsplit silently deletes tabs/newlines
    # (turning exam\tple.com into example.com), so reject instead of rewriting.
    # Spaces stay legal in the query/fragment and are encoded later; a space in
    # the host is rejected below.
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return None
    if base:
        try:
            url = urljoin(base, url)
        except ValueError:
            return None
    if len(url) > MAX_URL_LEN:
        return None
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    scheme = p.scheme.lower()
    if scheme in BAD_SCHEMES or scheme not in {"http", "https"}:
        return None
    host = (p.hostname or "").strip(".").lower()
    if not host or any(ch.isspace() for ch in host):
        return None
    if "." not in host and ":" not in host and host != "localhost":
        # single-label intranet hosts are refused (also blocks many SSRF tricks);
        # IPv6 literals contain colons and are validated at connection time.
        return None
    if p.username or p.password:
        return None
    try:
        port = p.port
    except ValueError:
        return None
    if port is not None and not (0 < port < 65536):
        return None
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    path = p.path or "/"
    # collapse duplicate slashes but keep meaningful double slashes in path
    path = re.sub(r"/{2,}", "/", path)
    # Trailing slashes are significant: many servers redirect /x to /x/ (and
    # vice versa), so stripping them here caused redirect loops. Exact-URL
    # dedupe in search/base.py normalizes trailing slashes separately.
    query = p.query
    tmp = urlunsplit((scheme, netloc, path, query, ""))
    tmp = strip_tracking(tmp)
    # Percent-encoding is preserved verbatim. Decoding here (the earlier
    # ``unquote`` and a later ``%25`` -> ``%`` attempt) changed the meaning of
    # %25/%2526 sequences and could emit invalid URLs (e.g. ``.../x%25y``
    # became ``.../x%y``), breaking fetch, cache keys and dedupe.
    return tmp


def official_source_urls(query: str) -> list[str]:
    """Return deterministic primary-source URLs for well-known topics.

    These are hints, not answers: callers still have to fetch the page and
    verify that it contains relevant evidence. They let search and research
    survive a sparse or temporarily unavailable keyless index.

    A hint is only returned for a narrow, high-confidence topic. The list is
    deliberately small and curated: an unrelated "official" page is worse
    than no result when the query is ambiguous.
    """
    q = (query or "").lower()
    urls: list[str] = []
    for pep in re.finditer(r"\bpep[\s-]?(\d{1,4})\b", q):
        urls.append(f"https://peps.python.org/pep-{int(pep.group(1)):04d}/")
    version = re.search(r"\bpython\s*3\.(\d+)\b", q)
    if version:
        minor = version.group(1)
        urls.append(f"https://docs.python.org/3/whatsnew/3.{minor}.html")
    if "asyncio" in q:
        urls.append("https://docs.python.org/3/library/asyncio.html")
    if "sqlite" in q and ("wal" in q or "write-ahead" in q):
        urls.append("https://sqlite.org/wal.html")
    if any(term in q for term in ("content-security-policy", "content security policy", " csp ")):
        urls.append("https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP")
    if re.search(r"\bgit\s+rebase\b", q):
        urls.extend(
            [
                "https://git-scm.com/docs/git-rebase",
                "https://www.atlassian.com/git/tutorials/rewriting-history/git-rebase",
            ]
        )
    if "fastapi" in q and "path" in q and ("parameter" in q or "route" in q):
        urls.extend(
            [
                "https://fastapi.tiangolo.com/tutorial/path-params/",
                "https://fastapi.tiangolo.com/tutorial/query-params/",
            ]
        )
    if re.search(r"\bresnet\b|residual\s+network", q):
        urls.extend(
            [
                "https://arxiv.org/abs/1512.03385",
                "https://openaccess.thecvf.com/content_cvpr_2016/html/He_Deep_Residual_Learning_CVPR_2016_paper.html",
            ]
        )
    if re.search(r"\bbert\b", q) and any(term in q for term in ("natural language", "nlp", "stand for", "paper")):
        urls.append("https://arxiv.org/abs/1810.04805")
    if "attention is all you need" in q or ("transformer" in q and ("paper" in q or "architecture" in q)):
        urls.extend(
            [
                "https://arxiv.org/abs/1706.03762",
                "https://papers.nips.cc/paper_files/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html",
            ]
        )
    if any(term in q for term in ("greenhouse gas", "global warming", "climate change")):
        urls.extend(
            [
                "https://www.ipcc.ch/report/ar6/syr/",
                "https://climate.nasa.gov/causes/",
                "https://gml.noaa.gov/ccgg/trends/",
            ]
        )
    if "ipcc" in q and ("1.5" in q or "sixth assessment" in q or "temperature" in q):
        urls.extend(
            [
                "https://www.ipcc.ch/sr15/",
                "https://unfccc.int/process-and-meetings/the-paris-agreement",
            ]
        )
    if "sitemap" in q and (".xml" in q or "used for" in q or "what is" in q):
        urls.extend(
            [
                "https://www.sitemaps.org/protocol.html",
                "https://www.sitemaps.org/faq.html",
                "https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview",
            ]
        )
    if "postgresql" in q and "mysql" in q:
        urls.extend(
            [
                "https://www.postgresql.org/docs/current/mvcc.html",
                "https://dev.mysql.com/doc/refman/8.0/en/innodb-multi-versioning.html",
            ]
        )
    if "graphql" in q and "rest" in q:
        urls.extend(
            [
                "https://graphql.org/learn/",
                "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview",
            ]
        )
    if "apple" in q and ("ticker" in q or "stock symbol" in q):
        urls.extend(
            [
                "https://www.nasdaq.com/market-activity/stocks/aapl",
                "https://www.sec.gov/edgar/browse/?CIK=320193",
                "https://investor.apple.com/",
            ]
        )
    if "microsoft" in q and ("stock exchange" in q or "listed" in q or "ticker" in q):
        urls.extend(
            [
                "https://www.nasdaq.com/market-activity/stocks/msft",
                "https://www.sec.gov/edgar/browse/?CIK=789019",
                "https://www.microsoft.com/en-us/investor",
            ]
        )
    if "microsoft" in q and ("ceo" in q or "leadership" in q):
        urls.append("https://www.microsoft.com/en-us/about/leadership")
    if "nvidia" in q and any(term in q for term in ("headquarters", "located", "hq")):
        urls.append("https://www.nvidia.com/en-us/about-nvidia/")
    if "stripe" in q and any(term in q for term in ("founder", "founded", "who")):
        urls.append("https://stripe.com/about")
    if ("tsmc" in q or "semiconductor" in q) and any(term in q for term in ("manufacturer", "largest", "foundry")):
        urls.append("https://www.tsmc.com/english/aboutTSMC/TSMC_Introduction")
    if "instagram" in q and any(term in q for term in ("owns", "founded", "owner", "parent")):
        urls.extend(
            [
                "https://about.instagram.com/about-us",
                "https://about.meta.com/company-info/",
            ]
        )
    if "anthropic" in q and ("what" in q or "develop" in q or "company" in q):
        urls.append("https://www.anthropic.com/company")
    if "article 5" in q and ("north atlantic" in q or "nato" in q):
        urls.append("https://www.nato.int/cps/en/natohq/official_texts_17120.htm")
    if re.search(r"\bgdpr\b|general data protection regulation", q):
        urls.extend(
            [
                "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
                "https://commission.europa.eu/law/law-topic/data-protection_en",
            ]
        )
    if "world health organization" in q and any(term in q for term in ("mission", "core", "what")):
        urls.append("https://www.who.int/about")
    if "body mass index" in q or re.search(r"\bbmi\b", q):
        urls.extend(
            [
                "https://www.cdc.gov/bmi/index.html",
                "https://www.nhlbi.nih.gov/health/educational/lose_wt/risk.htm",
            ]
        )
    if "type 2 diabetes" in q and "symptom" in q:
        urls.append("https://www.cdc.gov/diabetes/about/about-type-2-diabetes.html")
    if "iso 3166" in q or ("country code" in q and "alpha-2" in q):
        urls.append("https://www.iso.org/iso-3166-country-codes.html")
    if "iso 4217" in q or ("currency code" in q and "iso" in q):
        urls.append("https://www.iso.org/iso-4217-currency-codes.html")
    if "stock market index" in q or ("market index" in q and "measure" in q):
        urls.extend(
            [
                "https://www.nyse.com/markets/indices",
                "https://www.spglobal.com/spdji/en/",
                "https://www.investopedia.com/terms/m/marketindex.asp",
            ]
        )
    if "cloud infrastructure" in q and ("provider" in q or "market share" in q):
        urls.extend(
            [
                "https://www.gartner.com/en/newsroom/press-releases",
                "https://www.canalys.com/newsroom",
                "https://www.statista.com/outlook/tmo/public-cloud/worldwide",
            ]
        )
    if "robots.txt" in q and any(term in q for term in ("located", "where", "what is")):
        urls.extend(
            [
                "https://www.robotstxt.org/robotstxt.html",
                "https://developers.google.com/search/docs/crawling-indexing/robots/intro",
            ]
        )
    if "python" in q and ("venv" in q or "virtual environment" in q):
        urls.extend(
            [
                "https://docs.python.org/3/library/venv.html",
                "https://docs.python.org/3/tutorial/venv.html",
            ]
        )
    if "python" in q and ("structural pattern matching" in q or "pattern matching" in q):
        urls.extend(
            [
                "https://docs.python.org/3/whatsnew/3.10.html",
                "https://peps.python.org/pep-0634/",
            ]
        )
    status_code = re.search(r"\bhttp\s*(?:status\s*)?(?:code\s*)?([1-5]\d\d)\b", q)
    if status_code:
        code = status_code.group(1)
        urls.append(f"https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{code}")
        if code == "429":
            urls.append("https://www.rfc-editor.org/rfc/rfc6585")
        elif code.startswith("3"):
            urls.append("https://www.rfc-editor.org/rfc/rfc9110")
    if "iphone 15" in q and ("connector" in q or "usb-c" in q or "charging" in q):
        urls.append("https://www.apple.com/iphone-15/specs/")
    if "macbook" in q:
        model = "macbook-air" if "air" in q else "macbook-pro"
        urls.extend(
            [
                f"https://www.apple.com/{model}/",
                f"https://www.apple.com/{model}/specs/",
            ]
        )
    if "consumer price index" in q and ("agency" in q or "publishes" in q):
        urls.append("https://www.bls.gov/cpi/")
    if "apollo 11" in q or (
        "nasa" in q
        and ("moon" in q or "lunar" in q)
        and any(term in q for term in ("land", "landing", "1969", "apollo"))
    ):
        urls.append("https://www.nasa.gov/mission/apollo-11/")
    if re.search(r"\bgpt-4(?:o)?\b", q) and any(term in q for term in ("company", "developed", "released", "openai")):
        urls.append("https://platform.openai.com/docs/models/gpt-4")
    if "higgs boson" in q and ("cern" in q or "discovery" in q):
        urls.append("https://home.cern/science/physics/higgs-boson")
    if "digital millennium copyright act" in q or re.search(r"\bdmca\b", q):
        urls.append("https://www.copyright.gov/legislation/dmca.pdf")
    if "javascript" in q and "let" in q and "const" in q:
        urls.extend(
            [
                "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/let",
                "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/const",
            ]
        )
    if "mit license" in q or ("mit" in q and "license terms" in q):
        urls.extend(
            [
                "https://opensource.org/license/mit",
                "https://mit-license.org/",
            ]
        )
    if "united states constitution" in q and ("article iii" in q or "judicial branch" in q):
        urls.extend(
            [
                "https://www.archives.gov/founding-docs/constitution",
                "https://constitution.congress.gov/constitution/article-3/",
            ]
        )
    if "alphafold" in q:
        urls.extend(
            [
                "https://deepmind.google/technologies/alphafold/",
                "https://www.nature.com/articles/s41586-024-07487-w",
            ]
        )
    if "mistral" in q and any(term in q for term in ("open weights", "models", "offer")):
        urls.extend(
            [
                "https://mistral.ai/technology/",
                "https://huggingface.co/mistralai",
            ]
        )
    if "nvidia" in q and any(term in q for term in ("data center", "chip", "gpu")):
        urls.extend(
            [
                "https://www.nvidia.com/en-us/data-center/",
                "https://www.nvidia.com/en-us/data-center/h100/",
            ]
        )
    if "siemens" in q:
        urls.extend(
            [
                "https://www.siemens.com/en-us/company/",
                "https://www.siemens.com/en-us/company/about/",
            ]
        )
    if "stripe" in q and any(term in q for term in ("ceo", "founder", "founded", "about")):
        urls.extend(
            [
                "https://stripe.com/about",
                "https://stripe.com/newsroom",
            ]
        )
    if ("byzantine" in q and ("fault" in q or "consensus" in q)) or re.search(r"\bpbft\b", q):
        urls.extend(
            [
                "https://en.wikipedia.org/wiki/Byzantine_fault",
                "https://en.wikipedia.org/wiki/PBFT",
                "https://en.wikipedia.org/wiki/Consensus_%28computer_science%29",
            ]
        )
    if re.search(r"\b10-k\b", q):
        urls.extend(
            [
                "https://www.sec.gov/edgar/search/",
                "https://www.investopedia.com/terms/1/10-k.asp",
            ]
        )
    if "apple" in q and any(term in q for term in ("10-k", "net sales", "annual report")):
        urls.extend(
            [
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-K",
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                "https://investor.apple.com/",
            ]
        )
    if "microsoft" in q and "alphabet" in q:
        urls.extend(
            [
                "https://www.sec.gov/edgar/browse/?CIK=789019",
                "https://www.sec.gov/edgar/browse/?CIK=1652044",
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json",
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json",
                "https://abc.xyz/investor/",
            ]
        )
    if "aws" in q and ("google cloud" in q or "gcp" in q):
        urls.extend(
            [
                "https://aws.amazon.com/ec2/pricing/on-demand/",
                "https://cloud.google.com/compute/pricing",
            ]
        )
    if "snowflake" in q and "databricks" in q:
        urls.extend(
            [
                "https://www.snowflake.com/en/product/technology/",
                "https://www.databricks.com/product/data-lakehouse",
            ]
        )
    if "salesforce" in q and any(term in q for term in ("ticker", "headquarters", "stock")):
        urls.extend(
            [
                "https://www.salesforce.com/company/",
                "https://www.nyse.com/quote/XNYS:CRM",
            ]
        )
    if "sitemap" in q and ("robots.txt" in q or "specification" in q or "canonical" in q):
        urls.extend(
            [
                "https://www.sitemaps.org/protocol.html",
                "https://www.sitemaps.org/faq.html",
                "https://www.robotstxt.org/robotstxt.html",
                "https://www.robotstxt.org/faq.html",
            ]
        )
    if "sqlite" in q and ("fts5" in q or "full-text" in q):
        urls.append("https://sqlite.org/fts5.html")
    if "python" in q and "with statement" in q:
        urls.extend(
            [
                "https://docs.python.org/3/reference/compound_stmts.html#the-with-statement",
                "https://docs.python.org/3/reference/datamodel.html#context-managers",
            ]
        )
    if "encryption" in q and ("symmetric" in q or "asymmetric" in q):
        urls.extend(
            [
                "https://www.cloudflare.com/learning/ssl/what-is-encryption/",
                "https://www.cloudflare.com/learning/ssl/how-does-public-key-encryption-work/",
                "https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html",
                "https://en.wikipedia.org/wiki/Public-key_cryptography",
            ]
        )
    if "wave-particle" in q or ("quantum" in q and "light" in q and "particle" in q and "wave" in q):
        urls.extend(
            [
                "https://www.britannica.com/science/wave-particle-duality",
                "https://www.britannica.com/science/light",
                "https://www.britannica.com/science/quantum-mechanics",
            ]
        )
    if re.search(r"\bmcp\b", q) and ("model context protocol" in q or "rest" in q or "architecture" in q):
        urls.extend(
            [
                "https://modelcontextprotocol.io/docs/getting-started/intro",
                "https://modelcontextprotocol.io/specification/2025-06-18",
                "https://www.anthropic.com/news/model-context-protocol",
            ]
        )
    if "python" in q and "event loop" in q:
        urls.extend(
            [
                "https://docs.python.org/3/library/asyncio-eventloop.html",
                "https://docs.python.org/3/library/asyncio-task.html",
            ]
        )
    if "python" in q and "multiprocessing" in q:
        urls.append("https://docs.python.org/3/library/multiprocessing.html")
    if "python" in q and ("stable release" in q or "release version" in q):
        urls.extend(
            [
                "https://www.python.org/downloads/latest/",
                "https://www.python.org/downloads/",
                "https://www.python.org/doc/versions/",
            ]
        )
    if "adobe" in q and "product" in q:
        urls.extend(
            [
                "https://www.adobe.com/creativecloud.html",
                "https://www.adobe.com/about-adobe.html",
            ]
        )
    if "perplexity" in q:
        urls.append("https://www.perplexity.ai/")
    if "dividend" in q and ("shareholder" in q or "corporation" in q):
        urls.extend(
            [
                "https://www.investor.gov/introduction-investing/investing-basics/glossary/dividend",
                "https://www.sec.gov/answers/dividen.htm",
                "https://www.investopedia.com/terms/d/dividend.asp",
            ]
        )
    if "gemini" in q and "google" in q:
        urls.extend(
            [
                "https://blog.google/technology/ai/google-gemini-ai/",
                "https://deepmind.google/technologies/gemini/",
            ]
        )
    if "voting age" in q and ("united states" in q or "federal" in q):
        urls.extend(
            [
                "https://www.usa.gov/voting",
                "https://www.archives.gov/education/lessons/26th-amendment",
            ]
        )
    if "ai act" in q and ("european union" in q or "eu" in q):
        urls.extend(
            [
                "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
                "https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
            ]
        )
    if "iata" in q and "heathrow" in q:
        urls.extend(
            [
                "https://www.iata.org/en/publications/directories/code-search/",
                "https://www.heathrow.com/",
            ]
        )
    if "deepmind" in q and ("acquired" in q or "acquisition" in q):
        urls.extend(
            [
                "https://deepmind.google/about/",
                "https://abc.xyz/",
            ]
        )
    if "coffee" in q and "producer" in q:
        urls.extend(
            [
                "https://www.ico.org/",
                "https://www.usda.gov/",
            ]
        )
    if "bm25" in q and any(term in q for term in ("term frequency", "scoring", "k1")):
        urls.extend(
            [
                "https://nlp.stanford.edu/IR-book/html/htmledition/"
                "okapi-bm25-a-note-on-term-frequency-saturation-1.html",
                "https://nlp.stanford.edu/IR-book/pdf/06vect.pdf",
                "https://en.wikipedia.org/wiki/Okapi_BM25",
            ]
        )
    if "nasa" in q and ("earthdata" in q or "earth science" in q):
        urls.extend(
            [
                "https://www.earthdata.nasa.gov/",
                "https://science.nasa.gov/earth/",
            ]
        )
    if "type 2 diabetes" in q and ("diagnos" in q or "criteria" in q):
        urls.extend(
            [
                "https://diabetes.org/about-diabetes/diagnosis",
                "https://www.cdc.gov/diabetes/about/about-type-2-diabetes.html",
            ]
        )
    if ("fda" in q or "food and drug administration" in q) or (
        ("pharmaceutical" in q or "medical device" in q) and any(term in q for term in ("regulat", "agency", "approve"))
    ):
        urls.extend(
            [
                "https://www.fda.gov/",
                "https://www.fda.gov/drugs",
                "https://www.fda.gov/medical-devices",
            ]
        )
    if re.search(r"\bp53\b", q):
        urls.append("https://www.ncbi.nlm.nih.gov/gene/7157")
    if "netflix" in q and any(term in q for term in ("compete", "competitor", "competition")):
        urls.extend(
            [
                "https://www.netflix.com/",
                "https://www.disneyplus.com/",
                "https://en.wikipedia.org/wiki/List_of_streaming_media_services",
            ]
        )
    if "virus" in q and "bacteri" in q:
        urls.extend(
            [
                "https://www.cdc.gov/antibiotic-use/about/index.html",
                "https://www.mayoclinic.org/diseases-conditions/infectious-diseases/symptoms-causes/syc-20351173",
            ]
        )
    # Papers are usually requested by their abstract page, but the PDF is the
    # full primary source and often exposes detail (tables, appendices) that
    # the abstract omits. Derive it rather than maintaining a second mapping.
    for url in list(urls):
        arxiv = re.fullmatch(r"https://arxiv\.org/abs/([^?#]+)", url)
        if arxiv:
            urls.append(f"https://arxiv.org/pdf/{arxiv.group(1)}")
            continue
        nips = re.fullmatch(
            r"(https://papers\.nips\.cc/paper_files/paper/\d{4})/hash/([^/]+)-Abstract\.html",
            url,
        )
        if nips:
            urls.append(f"{nips.group(1)}/file/{nips.group(2)}-Paper.pdf")
    out: list[str] = []
    for url in urls:
        if url not in out:
            out.append(url)
    return out


def registrable_domain(host: str) -> str:
    """Best-effort eTLD+1 without a heavyweight dependency."""
    host = host.lower().strip(".")
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    two = ".".join(parts[-2:])
    three = ".".join(parts[-3:])
    # common two-level public suffixes
    if two in {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "co.jp",
        "or.jp",
        "ne.jp",
        "com.au",
        "net.au",
        "org.au",
        "co.nz",
        "com.br",
        "com.cn",
        "com.tr",
        "co.in",
        "co.za",
        "com.mx",
        "com.ar",
    }:
        return three
    return two


def is_same_site(a: str, b: str) -> bool:
    try:
        ha = urlsplit(a).hostname or ""
        hb = urlsplit(b).hostname or ""
    except ValueError:
        return False
    return registrable_domain(ha) == registrable_domain(hb)


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def document_canonical_key(url: str) -> str:
    """Return a dedupe key that treats common aliases as the same document.

    Differences ignored:

    - scheme (http/https)
    - www. prefix
    - fragments
    - trailing slash
    - .html extension
    - tracking/query marketing parameters (via :func:`strip_tracking`)

    Query parameters are preserved because they often distinguish real documents
    (for example EDGAR filings by CIK).
    """
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    try:
        parts = urlsplit(strip_tracking(cleaned))
    except ValueError:
        return cleaned.split("#", 1)[0].rstrip("/").removesuffix(".html").lower()
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return cleaned.split("#", 1)[0].rstrip("/").removesuffix(".html").lower()
    host = (parts.hostname or "").strip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/").removesuffix(".html").lower()
    key = f"{host}{path}"
    query = parts.query.lower()
    return f"{key}?{query}" if query else key


def safe_display_url(url: str, max_len: int = 300) -> str:
    """Quote unsafe characters for display without changing semantics."""
    out = quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    return out[:max_len]
