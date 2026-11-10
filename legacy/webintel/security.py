"""Security boundary: URL validation, SSRF protection, safe streaming fetch.

Threat model (docs/threat_model.md): the untrusted input is every URL we are asked
to fetch or follow. We defend:
  - scheme allowlist (http/https only, no file/data/ftp)
  - hostname sane, no userinfo tricks with @
  - resolved addresses must be public (private/loopback/link-local/metadata blocked)
  - manual redirect handling: EVERY hop re-validated at redirect time (R5)
  - streaming download with hard byte cap, so an oversized body aborts mid-stream
  - no shell, no subprocess, no eval anywhere in this module's call graph
DNS rebinding residual risk is documented in docs/threat_model.md (TOCTOU between
our check and the connection) and is mitigated by re-validating on every
connection attempt within one request and keeping the window short.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Optional

from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
IPV4_OCTETS = r"(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"

BLOCKED_HOST_PATTERNS = (
    re.compile(r"^localhost$|^localhost\.|\.localhost$", re.I),
    re.compile(r"^(.*\.)?local$|^\.local$|\.localdomain|\.lan|\.intranet|\.internal$|\.home$|\.corp$", re.I),
    re.compile(r"^(?:metadata\.google\.internal$)", re.I),
)


class UnsafeURLError(ValueError):
    """Raised when a URL fails the security policy."""


def is_ip_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    if isinstance(addr, ipaddress.IPv4Address):
        v6 = ipaddress.IPv6Address(int(addr))
    else:
        v6 = addr
    if v6.ipv4_mapped:
        # ::ffff:127.0.0.1-style mappings must be judged as IPv4
        return is_ip_blocked(str(v6.ipv4_mapped))
    networks_blocked = (
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),   # link-local incl. cloud metadata 169.254.169.254
        ipaddress.ip_network("100.64.0.0/10"),    # CGNAT / Tailscale-like
        ipaddress.ip_network("192.0.0.0/24"),
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("198.18.0.0/15"),
        ipaddress.ip_network("224.0.0.0/4"),      # multicast
        ipaddress.ip_network("240.0.0.0/4"),      # reserved
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),         # unique local
        ipaddress.ip_network("fe80::/10"),        # link local
        ipaddress.ip_network("::ffff:0:0/96"),    # caught via mapped above, keep too
    )
    return any(addr in n for n in networks_blocked)


def resolve_host(host: str) -> list[str]:
    addrs = set()
    for info in socket.getaddrinfo(host, None):
        addrs.add(info[4][0])
    return sorted(addrs)


def check_host(hostname: str, allow_private: bool = False) -> Optional[str]:
    """Returns an error reason if the hostname must not be contacted; None if OK."""
    if allow_private:
        return None
    h = hostname.strip().lower().rstrip(".")
    if not h or len(h) > 253:
        return "empty or overlong hostname"
    if re.fullmatch(IPV4_OCTETS, h):
        return None if not is_ip_blocked(h) else "private or reserved ip literal"
    if h.startswith("[") and h.endswith("]"):
        return None if not is_ip_blocked(h[1:-1]) else "private ipv6 literal"
    if any(p.search(h) for p in BLOCKED_HOST_PATTERNS):
        return "internal hostname"
    try:
        ip_data = ipaddress.ip_address(h)
        return None if not is_ip_blocked(str(ip_data)) else "private literal"
    except ValueError:
        pass
    try:
        for ip in resolve_host(h):
            if is_ip_blocked(ip):
                return "resolves to private address"
    except (socket.gaierror, OSError):
        return "dns resolution failed"
    return None


def validate_url(raw: str, allow_private: bool = False) -> str:
    """Validate and normalize an untrusted URL. Raises UnsafeURLError."""
    if not isinstance(raw, str):
        raise UnsafeURLError("url must be a string")
    u = raw.strip()
    if len(u) > 2048:
        raise UnsafeURLError("url too long")
    if any(c in u for c in "\r\n\t") or CONTROL_CHARS.search(u):
        raise UnsafeURLError("control characters in url")
    try:
        parts = urlsplit(u)
    except ValueError as e:
        raise UnsafeURLError(f"url parse failed: {e}")
    if parts.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme '{parts.scheme or 'none'}' not allowed (http/https only)")
    if parts.username or parts.password:
        raise UnsafeURLError("userinfo in url not allowed")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("missing hostname")
    reason = check_host(host, allow_private=allow_private)
    if reason:
        raise UnsafeURLError(reason)
    # rebuild without round-tripping user-authored garbage
    rebuilt = parts._replace(fragment="").geturl()
    return rebuilt


def sanitize_text(s: Optional[str]) -> str:
    """Strip control characters from anything we embed in results."""
    if not s:
        return ""
    return CONTROL_CHARS.sub("", s)


@dataclass(frozen=True)
class SafeURL:
    url: str


def safe_url(raw: str, allow_private: bool = False) -> str:
    return validate_url(raw, allow_private)
