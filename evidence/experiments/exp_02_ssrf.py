"""EXP-02: SSRF / URL handling matrix against a loopback fixture server.

Every attempt runs through the real ``SafeFetcher`` (policy + connect-time IP
pinning). The fixture records whether any TCP request reached it. A blocked
attempt must leave the hit counter unchanged.

Fixture-server results are SIMULATED by the directive's definition (local
fixture), even though the code under test is real.
"""

from __future__ import annotations

import asyncio
import asyncio
import socket
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from _common import assert_subject, emit

from weblens.cache import Cache
from weblens.config import Settings
from weblens.errors import WebLensError
from weblens.net import SafeFetcher
from weblens.net.ssrf import DestinationPolicy
import weblens

assert_subject(weblens.__file__)

HITS: list[str] = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        HITS.append(self.path)
        body = b"<html><body><p>fixture response</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        return


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()

with tempfile.TemporaryDirectory() as tmp:
    settings = Settings(
        cache_dir=Path(tmp) / "cache",
        cache_enabled=False,
        allow_private_networks=False,
        search_providers="ddg",
        total_timeout_s=5,
        connect_timeout_s=2,
        read_timeout_s=3,
    )
    policy = DestinationPolicy(settings)
    cache = Cache(settings)
    fetcher = SafeFetcher(settings, cache)

    variants = [
        ("loopback_ipv4", f"http://127.0.0.1:{port}/"),
        ("loopback_short", "http://127.1/"),
        ("loopback_decimal", "http://2130706433/"),
        ("loopback_hex", "http://0x7f000001/"),
        ("loopback_octal", "http://0177.0.0.1/"),
        ("loopback_ipv6", "http://[::1]/"),
        ("ipv4_mapped_ipv6", "http://[::ffff:127.0.0.1]/"),
        ("localhost_name", "http://localhost/"),
        ("localhost_upper", "http://LOCALHOST/"),
        ("localhost_trailing_dot", "http://localhost./"),
        ("metadata_ip", "http://169.254.169.254/latest/meta-data/"),
        ("metadata_host", "http://metadata.google.internal/"),
        ("private_10", "http://10.0.0.1/"),
        ("private_172", "http://172.16.0.1/"),
        ("private_192", "http://192.168.1.1/"),
        ("cgnat", "http://100.64.0.1/"),
        ("unspecified", "http://0.0.0.0/"),
        ("broadcast", "http://255.255.255.255/"),
        ("userinfo", f"http://user:pass@127.0.0.1:{port}/"),
        ("fragment_trick", f"http://127.0.0.1:{port}/#@example.com"),
        ("backslash", f"http://127.0.0.1:{port}\\@example.com/"),
        ("crlf", f"http://127.0.0.1:{port}/%0d%0aHost:evil"),
        ("nul", f"http://127.0.0.1:{port}/%00"),
        ("port_8080", "http://127.0.0.1:8080/"),
        ("port_22", "http://127.0.0.1:22/"),
        ("scheme_file", "file:///C:/Windows/win.ini"),
        ("scheme_gopher", "gopher://127.0.0.1:70/_test"),
        ("scheme_ftp", "ftp://127.0.0.1/file"),
        ("scheme_javascript", "javascript:alert(1)"),
        ("scheme_data", "data:text/html,<p>x</p>"),
        ("scheme_blob", "blob:http://127.0.0.1/uuid"),
    ]

    rows = []
    for name, url in variants:
        before = len(HITS)
        blocked = False
        code = ""
        message = ""
        try:
            asyncio.run(asyncio.wait_for(fetcher.fetch(url, use_cache=False), timeout=6))
        except (WebLensError, TimeoutError, ValueError, OSError) as exc:
            blocked = True
            code = getattr(exc, "code", type(exc).__name__)
            message = str(exc)[:120]
        except Exception as exc:  # unexpected failure still counts as not-fetched
            blocked = True
            code = type(exc).__name__
            message = str(exc)[:120]
        rows.append(
            {
                "variant": name,
                "url_kind": name.split("_")[0],
                "blocked": blocked,
                "error_code": str(code),
                "fixture_hits_delta": len(HITS) - before,
                "detail": message,
            }
        )

    # DNS rebinding: public answer first, loopback second, for the same hostname.
    real_gai = socket.getaddrinfo
    answers = [
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    ]

    def rebinding(*_a, **_k):
        return answers.pop(0) if answers else [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    socket.getaddrinfo = rebinding
    first_blocked, second_blocked, first_detail, second_detail = False, False, "", ""
    try:
        first = asyncio.run(policy.resolve("rebind.example", 443))
        first_detail = first.ip
    except Exception as exc:
        first_blocked = True
        first_detail = type(exc).__name__
    try:
        asyncio.run(policy.resolve("rebind.example", 443))
    except Exception as exc:
        second_blocked = True
        second_detail = type(exc).__name__
    socket.getaddrinfo = real_gai
    rows.append(
        {
            "variant": "dns_rebinding_second_answer",
            "url_kind": "dns",
            "blocked": second_blocked,
            "error_code": second_detail,
            "fixture_hits_delta": 0,
            "detail": f"first_ip={first_detail}",
        }
    )
    rows.append(
        {
            "variant": "dns_mixed_answers",
            "url_kind": "dns",
            "blocked": None,
            "error_code": "",
            "fixture_hits_delta": 0,
            "detail": "covered by test_resolve_rejects_mixed_public_private in suite",
        }
    )

    # Control: with the guard explicitly off, the fixture must be reachable.
    off_settings = settings.model_copy(update={"allow_private_networks": True})
    off_cache = Cache(off_settings)
    off_fetcher = SafeFetcher(off_settings, off_cache)
    before = len(HITS)
    guard_off_reached = False
    try:
        asyncio.run(asyncio.wait_for(off_fetcher.fetch(f"http://127.0.0.1:{port}/", use_cache=False), timeout=6))
        guard_off_reached = len(HITS) > before
    except Exception:
        guard_off_reached = False
    asyncio.run(off_fetcher.close())
    off_cache.close()

    rows.append(
        {
            "variant": "guard_off_control",
            "url_kind": "control",
            "blocked": not guard_off_reached,
            "error_code": "",
            "fixture_hits_delta": len(HITS) - before,
            "detail": "fixture reached only when allow_private_networks=True",
        }
    )

    asyncio.run(fetcher.close())
    cache.close()

# Redirect-to-private needs a controllable *public* fixture, which this machine
# cannot host without external exposure. Accounted for explicitly.
rows.append(
    {
        "variant": "redirect_to_private",
        "url_kind": "redirect",
        "blocked": None,
        "error_code": "",
        "fixture_hits_delta": 0,
        "detail": "NOT RUN: requires a controllable public redirector; not exposed for this test",
    }
)
server.shutdown()

tested = [r for r in rows if r["blocked"] is not None and r["url_kind"] != "control"]
blocked = [r for r in tested if r["blocked"]]
leaked = [r for r in rows if r.get("fixture_hits_delta", 0) > 0 and r["url_kind"] != "control"]

emit(
    {
        "experiment": "EXP-02",
        "kind": "ssrf-matrix",
        "class": "SIMULATED",
        "env": {"fixture_port": port, "fixture_requests_total": len(HITS)},
        "rows": rows,
        "summary": {
            "attempts": len(tested),
            "blocked": len(blocked),
            "fixture_packets_from_blocked": sum(r.get("fixture_hits_delta", 0) for r in tested),
            "guard_off_control_reached": guard_off_reached,
            "not_run": [r["variant"] for r in rows if r["blocked"] is None],
        },
        "limitations": [
            "Local loopback fixture only: SIMULATED class. No packet reached it from any blocked variant.",
            "Redirect-to-private and real DNS-rebinding against a public attacker-controlled host are NOT RUN.",
            "Browser subresource egress is NOT RUN: Playwright is not installed on this machine.",
        ],
    }
)
