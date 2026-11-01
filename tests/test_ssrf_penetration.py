"""
SSRF Penetration Testing Suite
Tests that no private IP, loopback, link-local, or cloud metadata can be reached
through any code path in both engine and weblens stacks.
"""
from __future__ import annotations

import ipaddress

import pytest

from src.engine.security import is_ip_blocked, safe_fetch_url, validate_url_security
from src.weblens.config import get_settings
from src.weblens.net.ssrf import DestinationPolicy

BLOCKED_IPS = [
    "127.0.0.1", "0.0.0.0", "10.0.0.1", "10.255.255.254", "100.64.0.1",
    "127.255.255.255", "169.254.0.1", "169.254.169.254", "172.16.0.0",
    "172.31.255.255", "192.168.0.0", "192.168.255.255", "192.0.0.1",
    "192.0.2.1", "192.88.99.1", "198.18.0.1", "198.51.100.1", "203.0.113.1",
    "224.0.0.1", "240.0.0.1", "255.255.255.255", "::1", "::", "fe80::1",
    "ff02::1", "fc00::1",
]

ALLOWED_IPS = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]


@pytest.mark.parametrize("ip_str", BLOCKED_IPS)
def test_blocked_ip(ip_str: str) -> None:
    assert is_ip_blocked(ipaddress.ip_address(ip_str)) is True, f"{ip_str} should be blocked"


@pytest.mark.parametrize("ip_str", ALLOWED_IPS)
def test_allowed_ip(ip_str: str) -> None:
    assert is_ip_blocked(ipaddress.ip_address(ip_str)) is False, f"{ip_str} should NOT be blocked"


SSRF_URLS = [
    ("http://127.0.0.1/", "loopback IPv4"),
    ("http://127.0.0.1:8080/admin", "loopback IPv4 with port"),
    ("http://10.0.0.1/", "RFC 1918 10.x"),
    ("http://172.16.0.1/", "RFC 1918 172.16.x"),
    ("http://192.168.1.1/", "RFC 1918 192.168.x"),
    ("http://169.254.169.254/", "AWS metadata"),
    ("http://169.254.169.254/latest/meta-data/", "AWS metadata path"),
    ("http://0.0.0.0/", "current network"),
    ("http://[::1]/", "IPv6 loopback"),
    ("http://[fe80::1]/", "IPv6 link-local"),
    ("http://[::ffff:127.0.0.1]/", "IPv4-mapped IPv6 loopback"),
    ("file:///etc/passwd", "file scheme"),
    ("file:///C:/Windows/System32/drivers/etc/hosts", "file scheme Windows"),
    ("gopher://127.0.0.1:70/", "gopher scheme"),
    ("dict://localhost:11211/", "dict scheme"),
    ("ftp://127.0.0.1/", "ftp scheme"),
    ("http://metadata.google.internal/", "GCP metadata hostname"),
    ("http://instance-data.ec2.internal/", "EC2 metadata hostname"),
    ("http://kubernetes.default.svc/", "Kubernetes service"),
    ("http://localhost/", "localhost hostname"),
    ("http://localhost:3000/", "localhost hostname with port"),
    ("http://localhost.localdomain/", "localhost.localdomain"),
    ("http://127.0.0.1%2e1/", "URL-encoded dot in IP"),
    ("http://0177.0.0.1/", "octal IP notation"),
    ("http://0x7f000001/", "hex IP notation"),
    ("http://2130706433/", "decimal IP notation"),
    ("http://test.local/", ".local domain"),
    ("http://api.internal/", ".internal domain"),
    ("http://home.home.arpa/", ".home.arpa domain"),
    ("http://router.lan/", ".lan domain"),
    ("http://example.com:22/", "SSH port"),
    ("http://example.com:3306/", "MySQL port"),
    ("http://example.com:5432/", "PostgreSQL port"),
    ("http://example.com:6379/", "Redis port"),
    ("http://example.com:27017/", "MongoDB port"),
    ("http://user:pass@example.com/", "userinfo in URL"),
    ("https://example.com", "valid public HTTPS"),
    ("http://example.com", "valid public HTTP"),
    ("https://www.python.org/", "valid public with www"),
]

BLOCKED_PATTERNS = [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1",
    "169.254.169.254", "0.0.0.0", "[::1]", "[fe80::1]",
    "[::ffff:127.0.0.1]", "file://", "gopher://", "dict://",
    "ftp://", "metadata.google.internal", "instance-data.ec2.internal",
    "kubernetes.default.svc", "localhost", "localhost.localdomain",
    "%2e1", "0177.", "0x7f000001", "2130706433", ".local", ".internal",
    ".home.arpa", ".lan", ":22/", ":3306/", ":5432/", ":6379/", ":27017/",
    "user:pass",
]


@pytest.mark.parametrize("url_str, description", SSRF_URLS)
def test_validate_url_security(url_str: str, description: str) -> None:
    is_safe, reason, ips = validate_url_security(url_str)
    should_block = any(p in url_str.lower() for p in BLOCKED_PATTERNS)
    if should_block:
        assert is_safe is False, f"SSRF bypass: {description} ({url_str}) was allowed: {reason}"
        assert ips == [], f"SSRF bypass: {description} returned resolved IPs: {ips}"
    else:
        assert is_safe is True, f"False positive: {description} ({url_str}) was blocked: {reason}"


@pytest.mark.asyncio
@pytest.mark.parametrize("url_str", [
    "http://127.0.0.1:9999/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/",
    "file:///etc/passwd",
    "http://localhost:8080/",
])
async def test_safe_fetch_url_blocks_ssrf(url_str: str) -> None:
    with pytest.raises(PermissionError):
        await safe_fetch_url(url_str)


@pytest.fixture
def wl_policy():
    return DestinationPolicy(get_settings())


@pytest.mark.parametrize("hostname", [
    "localhost", "localhost.localdomain", "metadata", "metadata.google.internal",
    "metadata.goog", "instance-data", "instance-data.ec2.internal",
    "kubernetes.default", "kubernetes.default.svc",
])
def test_wl_blocked_hostnames(wl_policy: DestinationPolicy, hostname: str) -> None:
    with pytest.raises(Exception):
        wl_policy.check_hostname(hostname)


def test_wl_allowed_hostname(wl_policy: DestinationPolicy) -> None:
    wl_policy.check_hostname("example.com")
    wl_policy.check_hostname("www.python.org")


@pytest.mark.parametrize("port", [22, 25, 53, 8080, 3306, 5432, 6379, 27017])
def test_wl_blocked_ports(wl_policy: DestinationPolicy, port: int) -> None:
    with pytest.raises(Exception):
        wl_policy.check_port(port)


def test_wl_allowed_ports(wl_policy: DestinationPolicy) -> None:
    wl_policy.check_port(80)
    wl_policy.check_port(443)


@pytest.mark.asyncio
async def test_redirect_to_private_blocked() -> None:
    is_safe, reason, _ = validate_url_security("http://127.0.0.1:8080/")
    assert is_safe is False


@pytest.mark.asyncio
async def test_headless_browser_fallback_blocks_unsafe_url() -> None:
    from src.engine.extract.browser_fallback import fetch_rendered_dom
    ok, err = await fetch_rendered_dom("http://169.254.169.254/latest/meta-data/")
    assert ok is False
    assert "Security block" in err


@pytest.mark.asyncio
async def test_headless_browser_fallback_attaches_egress_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from unittest.mock import MagicMock
    from src.engine.extract.browser_fallback import fetch_rendered_dom

    captured_cmds: list[list[str]] = []

    def mock_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "<html><body>Proxied Content</body></html>"
        mock_res.stderr = ""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr("src.engine.extract.browser_fallback.find_browser_executable", lambda: "fake-chrome.exe")

    ok, html = await fetch_rendered_dom("https://example.com/safe-article")
    assert ok is True
    assert "Proxied Content" in html
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert any(arg.startswith("--proxy-server=http://127.0.0.1:") for arg in cmd)
    assert "--proxy-bypass-list=<-loopback>" in cmd

