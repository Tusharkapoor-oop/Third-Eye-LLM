from __future__ import annotations

import socket

import pytest

from weblens.errors import BlockedURLError
from weblens.net.ssrf import DestinationPolicy


@pytest.fixture
def policy(settings):
    return DestinationPolicy(settings)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.1.2.3",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "100.64.0.1",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_check_ip_blocks_non_public(policy, ip):
    with pytest.raises(BlockedURLError):
        policy.check_ip(ip)


@pytest.mark.parametrize("ip", ["1.1.1.1", "8.8.8.8", "2606:4700::1111"])
def test_check_ip_allows_public(policy, ip):
    policy.check_ip(ip)


def test_private_networks_can_be_enabled(settings):
    settings.allow_private_networks = True
    p = DestinationPolicy(settings)
    p.check_ip("127.0.0.1")
    p.check_port(8080)


@pytest.mark.parametrize(
    "host",
    ["localhost", "metadata.google.internal", "foo.internal", "router.local", "kubernetes.default"],
)
def test_check_hostname_blocks_internal_names(policy, host):
    with pytest.raises(BlockedURLError):
        policy.check_hostname(host)


def test_allowlist_and_denylist(settings):
    settings.allowed_hosts = "example.com"
    settings.block_hosts = "bad.example.com"
    p = DestinationPolicy(settings)
    p.check_hostname("docs.example.com")
    with pytest.raises(BlockedURLError):
        p.check_hostname("other.com")
    settings.block_hosts = "example.com"
    p = DestinationPolicy(settings)
    with pytest.raises(BlockedURLError):
        p.check_hostname("docs.example.com")


def test_only_web_ports_by_default(policy):
    policy.check_port(80)
    policy.check_port(443)
    with pytest.raises(BlockedURLError):
        policy.check_port(22)


def _addrinfo(*ips: str):
    out = []
    for ip in ips:
        if ":" in ip:
            out.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 443, 0, 0)))
        else:
            out.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)))
    return out


async def test_resolve_prefers_ipv4(monkeypatch, policy):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: _addrinfo("2606:4700::1111", "1.1.1.1"),
    )
    dest = await policy.resolve("example.com", 443)
    assert dest.ip == "1.1.1.1"


async def test_resolve_rejects_mixed_public_private(monkeypatch, policy):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: _addrinfo("1.1.1.1", "10.0.0.1"),
    )
    with pytest.raises(BlockedURLError):
        await policy.resolve("example.com", 443)


async def test_resolve_rejects_dns_failure(monkeypatch, policy):
    def fail(*a, **k):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(BlockedURLError):
        await policy.resolve("nope.example", 443)


async def test_resolve_does_not_connect_to_hostname(monkeypatch, policy):
    """The returned Destination must carry the validated IP, not the hostname."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("1.1.1.1"))
    dest = await policy.resolve("example.com", 443)
    assert dest.host == "example.com"
    assert dest.ip == "1.1.1.1"
