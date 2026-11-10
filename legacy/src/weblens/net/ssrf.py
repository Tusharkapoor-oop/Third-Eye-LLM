"""SSRF defence: destination validation at connection time.

The network backend resolves the hostname itself, rejects any non-public
destination, and then opens the TCP connection to the *validated IP*. TLS SNI
and the HTTP Host header still use the original hostname because httpcore
derives them from the request origin, not from the connected address.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import anyio
from httpcore._backends.anyio import AnyIOBackend

from ..config import Settings
from ..errors import BlockedURLError

# Hostnames that must never be resolved, even if DNS is subverted.
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
    "kubernetes.default",
    "kubernetes.default.svc",
}

# Cloud metadata endpoints that SSRF payloads commonly target.
BLOCKED_IPS = {
    "169.254.169.254",  # AWS / GCP / Azure IMDS
    "168.63.129.16",  # Azure WireServer
    "100.100.100.200",  # Alibaba Cloud metadata
}

BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home.arpa",
    ".lan",
)

# Ports a public web page is realistically served on. Anything else is refused
# unless private networks are explicitly enabled.
DEFAULT_PORTS = {80, 443}


@dataclass(frozen=True)
class Destination:
    host: str
    port: int
    ip: str


class DestinationPolicy:
    def __init__(self, settings: Settings):
        self.s = settings

    def check_url(self, url: str) -> None:
        try:
            parts = urlsplit(url)
        except Exception as e:
            raise BlockedURLError(f"invalid URL: {url}") from e
        if parts.scheme not in ("http", "https"):
            raise BlockedURLError(f"unsupported scheme: {parts.scheme}")
        host = parts.hostname or ""
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError as e:
            raise BlockedURLError(f"invalid URL port: {url}") from e
        self.check_hostname(host)
        self.check_port(port)

    def check_hostname(self, host: str) -> None:
        h = host.lower().strip(".")
        if not h:
            raise BlockedURLError("empty host")
        if h in BLOCKED_HOSTNAMES or any(h.endswith(sfx) for sfx in BLOCKED_SUFFIXES):
            raise BlockedURLError(f"blocked hostname: {h}")
        # Literal IPs bypass DNS; validate them here as well as at connect time
        # so browser routing (which cannot use our httpcore backend) is covered.
        try:
            addr = ipaddress.ip_address(h)
        except ValueError:
            pass
        else:
            self.check_ip(str(addr))
        deny = self.s.denylist
        if any(h == d or h.endswith("." + d) for d in deny):
            raise BlockedURLError(f"host denied by policy: {h}")
        allow = self.s.host_allowlist
        if allow and not any(h == a or h.endswith("." + a) for a in allow):
            raise BlockedURLError(f"host not in allowlist: {h}")

    def check_port(self, port: int) -> None:
        if self.s.allow_private_networks:
            return
        if port not in DEFAULT_PORTS:
            raise BlockedURLError(f"port not allowed: {port}")

    def check_ip(self, ip: str) -> None:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError as e:
            raise BlockedURLError(f"invalid IP: {ip}") from e
        if addr.version == 6 and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        # Cloud-metadata endpoints are never a legitimate destination, so they are
        # rejected BEFORE the private-network opt-in. Previously the opt-in
        # returned early and silently re-enabled 169.254.169.254, which is the one
        # address whose entire purpose is to hand out instance credentials.
        if str(addr) in BLOCKED_IPS:
            raise BlockedURLError(f"blocked metadata IP: {addr}")
        if self.s.allow_private_networks:
            return
        if not addr.is_global or addr.is_multicast or addr.is_reserved or addr.is_loopback:
            raise BlockedURLError(f"non-public destination: {ip}")
        if addr.is_link_local:
            raise BlockedURLError(f"link-local destination: {ip}")

    async def resolve(self, host: str, port: int) -> Destination:
        from ..config import Settings

        # Enforce the configured outbound allowlist/denylist at connection time
        # too, not only in the pre-check: a caller that reaches the transport
        # directly (SafeNetworkBackend) must not be able to bypass an egress
        # allowlist. Private/public IP ranges remain the second gate.
        policy = DestinationPolicy(
            Settings(
                allow_private_networks=self.s.allow_private_networks,
                allow_hosts=",".join(self.s.host_allowlist),
                block_hosts=",".join(self.s.denylist),
            )
        )
        policy.check_hostname(host)
        policy.check_port(port)
        try:
            infos = await anyio.to_thread.run_sync(lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except socket.gaierror as e:
            raise BlockedURLError(f"DNS resolution failed for {host}: {e}") from e
        if not infos:
            raise BlockedURLError(f"DNS returned no addresses for {host}")
        # Reject the whole hostname if any answer is non-public: a resolver that
        # alternates public/private answers must not be able to win a retry.
        ips: list[str] = []
        for info in infos:
            ip = str(info[4][0])
            policy.check_ip(ip)
            ips.append(ip)
        # Prefer IPv4 for stability on Windows dual-stack networks.
        chosen = next((i for i in ips if ":" not in i), ips[0])
        return Destination(host=host, port=port, ip=chosen)


class SafeNetworkBackend(AnyIOBackend):
    """httpcore backend that connects only to policy-approved destinations."""

    def __init__(self, policy: DestinationPolicy):
        self.policy = policy

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore backend API
        local_address: str | None = None,
        socket_options=None,
    ):
        dest = await self.policy.resolve(host, port)
        return await super().connect_tcp(
            dest.ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
