"""URL normalization, canonicalization and tracking-parameter removal.

Rules are deliberately conservative: never rewrite a URL in a way that could
change which resource is addressed, except for fragment removal and known
tracking parameters.
"""

from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

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
    if not host or ("." not in host and ":" not in host and host != "localhost"):
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
    tmp = unquote(tmp) if "%25" in tmp else tmp
    return tmp


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


def safe_display_url(url: str, max_len: int = 300) -> str:
    """Quote unsafe characters for display without changing semantics."""
    out = quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    return out[:max_len]
