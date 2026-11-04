"""Security, SSRF Guard, and Prompt Injection Defense Module.

Enforces connection-time SSRF / DNS rebinding defenses, streaming payload limits,
formula defanging, and indirect prompt injection quarantine.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from config import CONFIG

# Private and Cloud Metadata IP Networks
BLOCKED_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),       # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918 private
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918 private
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918 private
    ipaddress.ip_network("169.254.0.0/16"),    # IPv4 link-local / cloud metadata
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
)

BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
    "kubernetes.default",
    "kubernetes.default.svc",
})

# Indirect Prompt Injection Signatures
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+(override|prompt|directive)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a\s+developer|unrestricted|in\s+dan\s+mode)", re.IGNORECASE),
    re.compile(r"(reveal|print|exfiltrate|output)\s+(the\s+)?(api[_\s]?key|secret|password|env)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?safety\s+guidelines", re.IGNORECASE),
]


class SecurityValidationError(Exception):
    """Raised when a URL or payload violates security policies."""


def is_safe_ip(ip_str: str) -> bool:
    """Validate that an IP string is global, public, and not private/loopback."""
    try:
        addr = ipaddress.ip_address(ip_str)
        if addr.version == 6 and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        if not addr.is_global or addr.is_multicast or addr.is_reserved or addr.is_loopback or addr.is_link_local:
            return False
        return not any(addr in net for net in BLOCKED_NETWORKS)
    except ValueError:
        return False


def validate_url_security(url: str) -> tuple[str, int]:
    """Validate scheme, hostname, and port against SSRF and private network policies.

    Returns:
        tuple[str, int]: (hostname, port) if validated.
    Raises:
        SecurityValidationError: if scheme, host, or port are forbidden.
    """
    try:
        parts = urlsplit(url.strip())
    except Exception as exc:
        raise SecurityValidationError(f"Malformed URL: {exc}") from exc

    if parts.scheme.lower() not in ("http", "https"):
        raise SecurityValidationError(f"Forbidden URL scheme: {parts.scheme}")

    host = (parts.hostname or "").lower().strip(".")
    if not host:
        raise SecurityValidationError("Missing or empty hostname in URL")

    if host in BLOCKED_HOSTNAMES or any(host.endswith(sfx) for sfx in (".localhost", ".local", ".internal", ".lan")):
        raise SecurityValidationError(f"Blocked hostname: {host}")

    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    if port not in (80, 443, 8080, 8443):
        raise SecurityValidationError(f"Port {port} is not allowed for web extraction")

    # If host is an IP literal, validate immediately
    try:
        ipaddress.ip_address(host)
        if not is_safe_ip(host):
            raise SecurityValidationError(f"Forbidden private or loopback IP literal: {host}")
    except ValueError:
        pass  # Host is a DNS name, will be verified at resolution time

    return host, port


def validate_public_url(url: str) -> tuple[str, int]:
    """Validate that URL is safe, public, and not pointing to loopback or private networks."""
    return validate_url_security(url)


async def on_redirect_hook(response: httpx.Response) -> None:
    """Event hook to re-validate destination URL before following any HTTP redirect."""
    if response.is_redirect:
        location = response.headers.get("location")
        if location:
            from urllib.parse import urljoin
            target = urljoin(str(response.url), location)
            validate_public_url(target)


def safe_resolve_path(path_str: str, base_dir: Path | None = None) -> Path:
    """Validate and resolve a path preventing directory traversal and Windows device names.

    Raises:
        SecurityValidationError: if path escapes base directory or matches device names.
    """
    base = (base_dir or Path.cwd()).resolve()
    # Check for Windows reserved device names
    clean_stem = Path(path_str).stem.upper()
    reserved_devices = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if clean_stem in reserved_devices:
        raise SecurityValidationError(f"Forbidden Windows reserved device name: {clean_stem}")

    candidate = (base / path_str).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise SecurityValidationError(f"Path traversal detected: {path_str} escapes {base}") from exc

    return candidate


def resolve_and_verify_host(host: str, port: int) -> str:
    """Resolve hostname and ensure all returned IP addresses are public and safe.

    Returns:
        str: Validated IP address for connection pinning.
    Raises:
        SecurityValidationError: if DNS resolution fails or returns private IPs.
    """
    try:
        addrinfo = socket.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SecurityValidationError(f"DNS resolution failed for {host}: {exc}") from exc

    if not addrinfo:
        raise SecurityValidationError(f"No IP addresses returned for {host}")

    candidate_ips: list[str] = []
    for item in addrinfo:
        ip = str(item[4][0])
        if not is_safe_ip(ip):
            raise SecurityValidationError(f"DNS resolved {host} to forbidden non-public IP: {ip}")
        candidate_ips.append(ip)

    # Prefer IPv4 if available for local Windows dual-stack stability
    v4_ips = [ip for ip in candidate_ips if ":" not in ip]
    return v4_ips[0] if v4_ips else candidate_ips[0]


async def safe_fetch_url(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float | None = None,
    max_bytes: int | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Fetch URL with connection-time SSRF checks, redirect validation, and byte limits.

    Returns:
        tuple[int, dict[str, str], bytes]: (status_code, response_headers, body_bytes)
    """
    current_url = url
    max_redirects = 5
    req_headers = {
        "User-Agent": CONFIG.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        **(headers or {}),
    }
    timeout = timeout_s or CONFIG.read_timeout_s
    limit_bytes = max_bytes or CONFIG.max_response_bytes

    async with httpx.AsyncClient(
        follow_redirects=False,
        verify=True,
        timeout=httpx.Timeout(timeout, connect=CONFIG.connect_timeout_s),
    ) as client:
        for _ in range(max_redirects):
            host, port = validate_url_security(current_url)
            resolve_and_verify_host(host, port)

            async with client.stream("GET", current_url, headers=req_headers) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        break
                    from urllib.parse import urljoin
                    target_url = urljoin(current_url, location)
                    validate_public_url(target_url)
                    current_url = target_url
                    continue

                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > limit_bytes:
                    raise SecurityValidationError(f"Response size {content_length} exceeds limit of {limit_bytes} bytes")

                chunks: list[bytes] = []
                total_bytes = 0
                async for chunk in resp.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > limit_bytes:
                        raise SecurityValidationError(f"Response body exceeded maximum limit of {limit_bytes} bytes")
                    chunks.append(chunk)

                body = b"".join(chunks)
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status_code, resp_headers, body

    raise SecurityValidationError("Too many redirects")


def sanitize_untrusted_content(text: str) -> tuple[str, bool]:
    """Scan and quarantine indirect prompt injection patterns from web text.

    Returns:
        tuple[str, bool]: (sanitized_text, injection_detected)
    """
    detected = False
    clean_text = text

    for pattern in INJECTION_PATTERNS:
        if pattern.search(clean_text):
            detected = True
            clean_text = pattern.sub("[QUARANTINED_INSTRUCTION_OVERRIDE]", clean_text)

    # Strip dangerous HTML script / iframe tags if present
    clean_text = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", " ", clean_text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r"<\s*iframe[^>]*>.*?<\s*/\s*iframe\s*>", " ", clean_text, flags=re.DOTALL | re.IGNORECASE)

    return clean_text, detected


def defang_formula(val: str) -> str:
    """Defang spreadsheet formulas starting with =, +, -, @, tab, or carriage return."""
    if not val:
        return ""
    val_str = str(val).strip()
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + val_str
    return val_str

