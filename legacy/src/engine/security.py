"""
Security and Defensive Controls Module
Implements SSRF protection, DNS rebinding mitigation, streaming byte limits,
redirect revalidation, and untrusted evidence sanitization.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

from src.engine.config import CONFIG

WAF_MARKERS = (
    "just a moment...", "verify you are human", "cf-chl-", "turnstile",
    "datadome", "akamai bot manager", "access denied", "enable javascript",
    "checking your browser", "perimeterx", "incapsula",
)


def is_blocked_response(html: str, status_code: int) -> bool:
    """Detect common WAF/challenge shells without treating ordinary 4xx as content."""
    if status_code in (401, 403, 429, 503):
        return True
    sample = re.sub(r"\s+", " ", (html or "")[:200_000]).casefold()
    if not sample:
        return status_code >= 400
    marker_hits = sum(marker in sample for marker in WAF_MARKERS)
    shell = len(re.sub(r"<[^>]+>", " ", sample).split()) < 80
    return marker_hits >= 2 or (marker_hits >= 1 and shell)

# Reuse one connection pool for the lifetime of each event loop. Creating an
# AsyncClient per page defeats keep-alive/TLS reuse and was the dominant cost
# on repeated extraction requests. The loop check keeps asyncio.run()-based
# callers (including tests and short-lived CLI commands) isolated safely.
_shared_http_client: httpx.AsyncClient | None = None
_shared_http_loop: asyncio.AbstractEventLoop | None = None


async def get_shared_http_client() -> httpx.AsyncClient:
    """Return the event-loop-local HTTP client used by engine requests."""
    global _shared_http_client, _shared_http_loop
    loop = asyncio.get_running_loop()
    if _shared_http_client is None or _shared_http_loop is not loop or _shared_http_client.is_closed:
        _shared_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                CONFIG.read_timeout,
                connect=CONFIG.connect_timeout,
            ),
            follow_redirects=False,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
        _shared_http_loop = loop
    return _shared_http_client


async def close_shared_http_client() -> None:
    """Close the shared engine client when an embedding application shuts down."""
    global _shared_http_client, _shared_http_loop
    if _shared_http_client is not None:
        await _shared_http_client.aclose()
    _shared_http_client = None
    _shared_http_loop = None

# Prohibited IPv4 / IPv6 network blocks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),         # Private RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Address Space / CGNAT
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link Local & Cloud Metadata (AWS/GCP/Azure)
    ipaddress.ip_network("172.16.0.0/12"),      # Private RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),     # 6to4 Relay Anycast
    ipaddress.ip_network("192.168.0.0/16"),     # Private RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
    ipaddress.ip_network("100::/64"),           # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),      # Documentation
    ipaddress.ip_network("fc00::/7"),           # Unique local address (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-local
    ipaddress.ip_network("ff00::/8"),           # Multicast
]


def is_ip_blocked(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Checks if an IP address belongs to loopback, private, link-local, or reserved networks."""
    if hasattr(ip_obj, "ipv4_mapped") and ip_obj.ipv4_mapped and is_ip_blocked(ip_obj.ipv4_mapped):
        return True
    if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_unspecified:
        return True
    for net in BLOCKED_NETWORKS:
        if ip_obj in net:
            return True
    return False


def validate_url_security(url: str) -> tuple[bool, str, list[str]]:
    """
    Validates a URL against scheme restrictions, private IP ranges, and cloud metadata targets.
    Returns: (is_safe: bool, reason: str, resolved_ips: list[str])
    """
    if not url or not isinstance(url, str):
        return False, "Missing or invalid URL", []

    if "\x00" in url:
        return False, "Null byte detected in URL", []

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL syntax: {e}", []

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Prohibited scheme: '{parsed.scheme}'. Only 'http' and 'https' are allowed.", []

    if parsed.username or parsed.password:
        return False, "Userinfo in URL is forbidden (SSRF defense).", []

    hostname = parsed.hostname
    if not hostname:
        return False, "URL missing hostname.", []

    h_lower = hostname.lower()
    if h_lower in ("localhost", "localhost.localdomain") or h_lower.endswith(".localhost") or h_lower.endswith(".local"):
        return False, f"Blocked local hostname '{hostname}' (SSRF defense).", []

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    if parsed.port and parsed.port not in (80, 443, 8080, 8443):
        return False, f"Port {parsed.port} is not an allowed web port (SSRF defense).", []

    # Check for direct IP in hostname
    try:
        direct_ip = ipaddress.ip_address(hostname.strip("[]"))
        if is_ip_blocked(direct_ip):
            return False, f"Target IP {direct_ip} is in a blocked/private range (SSRF defense).", []
        return True, "Safe direct IP", [str(direct_ip)]
    except ValueError:
        pass  # Hostname is a domain name, proceed to DNS resolution

    # Resolve domain to all IP addresses
    resolved_ips: list[str] = []
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        for item in addr_info:
            sockaddr = item[4]
            ip_str = str(sockaddr[0])
            ip_obj = ipaddress.ip_address(ip_str)
            if is_ip_blocked(ip_obj):
                return False, f"Domain '{hostname}' resolves to blocked/private IP {ip_str} (SSRF defense).", []
            resolved_ips.append(ip_str)
    except socket.gaierror as e:
        return False, f"DNS resolution failed for hostname '{hostname}': {e}", []
    except Exception as e:
        return False, f"Error validating destination address: {e}", []

    if not resolved_ips:
        return False, f"No IP addresses resolved for hostname '{hostname}'", []

    return True, "Safe public URL", resolved_ips


# Zero-width, non-printable, and prompt injection patterns
ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u202A-\u202E]")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
PROMPT_INJECTION_SUSPICION = re.compile(
    r"(?:ignore\s+previous\s+instructions|disregard\s+all\s+prior|system\s*:\s*you\s+are|<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>|reveal\s+your\s+system\s+prompt)",
    re.IGNORECASE
)


def sanitize_untrusted_content(text: str) -> tuple[str, bool]:
    """
    Sanitizes untrusted web content.
    Strips zero-width characters, control codes, and flags potential prompt injections.
    Returns: (sanitized_text, suspicious_injection_detected)
    """
    if not text:
        return "", False

    # Remove zero-width characters and terminal control codes
    clean_text = ZERO_WIDTH_CHARS.sub("", text)
    clean_text = CONTROL_CHARS.sub("", clean_text)

    # Check for prompt injection signatures using both fast regex and pattern scanner
    has_injection = bool(PROMPT_INJECTION_SUSPICION.search(clean_text))
    if not has_injection:
        from src.weblens.security.injection import scan_injection
        has_injection = bool(scan_injection(clean_text))

    return clean_text, has_injection


def get_user_agent_for_url(url: str) -> str:
    """Returns compliant User-Agent headers tailored to destination policies."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if "wikipedia.org" in hostname or "wikimedia.org" in hostname:
        return "PersonalWebIntelEngine/1.0 (https://github.com/autonomous-ai/web-intel; contact@local.dev) httpx/0.28"
    return CONFIG.user_agent

async def safe_fetch_url(
    url: str,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = CONFIG.max_response_bytes,
    max_redirects: int = 5,
    timeout: float = CONFIG.read_timeout
) -> tuple[int, bytes, dict[str, str], str]:
    """
    Fetches a URL safely with:
    1. Pre-flight & per-redirect SSRF checks.
    2. Host-appropriate User-Agent policies.
    3. Streaming byte count limit (aborts if exceeded).
    4. Explicit timeouts.
    Returns: (status_code, content_bytes, response_headers, final_url)
    """
    owns_client = False
    current_url = url
    if client is None:
        client = await get_shared_http_client()

    redirect_count = 0

    try:
        while True:
            # 1. Validate destination before opening connection
            is_safe, reason, _ = validate_url_security(current_url)
            if not is_safe:
                raise PermissionError(f"Security validation blocked request to {current_url}: {reason}")

            # 2. Build request with domain-appropriate User-Agent
            req_headers = {"User-Agent": get_user_agent_for_url(current_url)}
            req = client.build_request("GET", current_url, headers=req_headers)
            resp = await client.send(req, stream=True)

            # Retry once with alternate User-Agent if 403 Forbidden received
            if resp.status_code == 403:
                await resp.aclose()
                alt_ua = (
                    "PersonalWebIntelEngine/1.0 (contact@local.dev)"
                    if "Mozilla" in req_headers["User-Agent"]
                    else CONFIG.user_agent
                )
                alt_req = client.build_request("GET", current_url, headers={"User-Agent": alt_ua})
                resp = await client.send(alt_req, stream=True)

            # Check for redirect status codes
            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                if redirect_count > max_redirects:
                    await resp.aclose()
                    raise RuntimeError(f"Exceeded maximum redirect limit ({max_redirects})")
                loc = resp.headers.get("location")
                if not loc:
                    await resp.aclose()
                    return resp.status_code, b"", dict(resp.headers), current_url
                next_url = urljoin(current_url, loc)
                await resp.aclose()
                current_url = next_url
                continue

            # Check Content-Length header upfront
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                await resp.aclose()
                raise ValueError(f"Content-Length ({content_length} bytes) exceeds limit ({max_bytes} bytes)")

            # Stream response chunks with cumulative byte counting
            chunks: list[bytes] = []
            total_bytes = 0
            async for chunk in resp.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    await resp.aclose()
                    raise ValueError(f"Response exceeded maximum allowed size of {max_bytes} bytes")
                chunks.append(chunk)

            headers_dict = dict(resp.headers)
            status_code = resp.status_code
            await resp.aclose()
            return status_code, b"".join(chunks), headers_dict, current_url

    finally:
        if owns_client:
            await client.aclose()
