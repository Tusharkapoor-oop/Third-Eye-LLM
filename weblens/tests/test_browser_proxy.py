"""Unit tests for the browser egress proxy's policy and tunnel behaviour."""

from __future__ import annotations

import asyncio

import pytest

from weblens.config import Settings
from weblens.net.browser_proxy import BrowserEgressProxy


async def _http_ok(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, seen: list[bytes]) -> None:
    request = await reader.readuntil(b"\r\n\r\n")
    seen.append(request)
    body = b"proxied"
    writer.write(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/plain\r\n"
        + f"Content-Length: {len(body)}\r\n".encode()
        + b"Connection: close\r\n\r\n"
        + body
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    data = await reader.readexactly(4)
    writer.write(data)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _http_echo_body(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, seen: list[bytes]) -> None:
    request = await reader.readuntil(b"\r\n\r\n")
    headers = {}
    for line in request.split(b"\r\n")[1:]:
        if b":" in line:
            key, value = line.split(b":", 1)
            headers[key.strip().lower()] = value.strip()
    body = await reader.readexactly(int(headers.get(b"content-length", b"0")))
    seen.append(body)
    response = b"body=" + body
    writer.write(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/plain\r\n"
        + f"Content-Length: {len(response)}\r\n".encode()
        + b"Connection: close\r\n\r\n"
        + response
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _server(handler) -> tuple[asyncio.AbstractServer, int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = int(next(iter(server.sockets)).getsockname()[1])
    return server, port


@pytest.mark.asyncio
async def test_http_request_is_forwarded_through_validated_ip():
    seen: list[bytes] = []

    async def handler(reader, writer):
        await _http_ok(reader, writer, seen)

    target, target_port = await _server(handler)
    proxy = BrowserEgressProxy(Settings(allow_private_networks=True, max_response_bytes=64_000))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(
            f"GET http://127.0.0.1:{target_port}/hello?x=1 HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{target_port}\r\n"
            "Connection: keep-alive\r\n\r\n".encode()
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        target.close()
        await target.wait_closed()

    assert response.startswith(b"HTTP/1.1 200 OK")
    assert response.endswith(b"proxied")
    assert seen
    assert b"GET /hello?x=1 HTTP/1.1" in seen[0]
    assert proxy.requests == 1


@pytest.mark.asyncio
async def test_private_destination_is_refused_before_connect():
    target, target_port = await _server(_echo)
    proxy = BrowserEgressProxy(Settings(allow_private_networks=False))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(f"GET http://127.0.0.1:{target_port}/ HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n\r\n".encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        target.close()
        await target.wait_closed()

    assert response.startswith(b"HTTP/1.1 403 Forbidden")


@pytest.mark.asyncio
async def test_http_post_body_is_forwarded():
    seen: list[bytes] = []

    async def handler(reader, writer):
        await _http_echo_body(reader, writer, seen)

    target, target_port = await _server(handler)
    proxy = BrowserEgressProxy(Settings(allow_private_networks=True))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(
            f"POST http://127.0.0.1:{target_port}/submit HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{target_port}\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 5\r\n\r\n"
            "hello".encode()
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        target.close()
        await target.wait_closed()

    assert response.startswith(b"HTTP/1.1 200 OK")
    assert response.endswith(b"body=hello")
    assert seen == [b"hello"]


@pytest.mark.asyncio
async def test_expect_100_continue_is_handled_before_reading_body():
    seen: list[bytes] = []

    async def handler(reader, writer):
        await _http_echo_body(reader, writer, seen)

    target, target_port = await _server(handler)
    proxy = BrowserEgressProxy(Settings(allow_private_networks=True))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(
            f"POST http://127.0.0.1:{target_port}/submit HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{target_port}\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: 5\r\n"
            "Expect: 100-continue\r\n\r\n".encode()
        )
        await writer.drain()
        interim = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        assert interim.startswith(b"HTTP/1.1 100 Continue")
        writer.write(b"hello")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        target.close()
        await target.wait_closed()

    assert response.startswith(b"HTTP/1.1 200 OK")
    assert response.endswith(b"body=hello")
    assert seen == [b"hello"]


@pytest.mark.asyncio
async def test_cleartext_upgrade_is_rejected():
    proxy = BrowserEgressProxy(Settings(allow_private_networks=True))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(
            b"GET http://127.0.0.1:9/ws HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9\r\n"
            b"Connection: Upgrade\r\n"
            b"Upgrade: websocket\r\n\r\n"
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()

    assert response.startswith(b"HTTP/1.1 400 Bad Request")


@pytest.mark.asyncio
async def test_non_absolute_http_target_is_rejected():
    proxy = BrowserEgressProxy(Settings(allow_private_networks=False))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(b"GET /only-a-path HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()

    assert response.startswith(b"HTTP/1.1 400 Bad Request")


@pytest.mark.asyncio
async def test_connect_upstream_failure_returns_error():
    proxy = BrowserEgressProxy(Settings(allow_private_networks=True, connect_timeout_s=2))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(b"CONNECT 127.0.0.1:1 HTTP/1.1\r\nHost: 127.0.0.1:1\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()

    assert response.startswith(b"HTTP/1.1 5")


@pytest.mark.asyncio
async def test_connect_tunnel_uses_validated_ip():
    target, target_port = await _server(_echo)
    proxy = BrowserEgressProxy(Settings(allow_private_networks=True))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n\r\n".encode())
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        writer.write(b"ping")
        await writer.drain()
        echoed = await asyncio.wait_for(reader.readexactly(4), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        target.close()
        await target.wait_closed()

    assert head.startswith(b"HTTP/1.1 200 Connection Established")
    assert echoed == b"ping"
    assert proxy.requests == 1


@pytest.mark.asyncio
async def test_private_connect_is_refused():
    target, target_port = await _server(_echo)
    proxy = BrowserEgressProxy(Settings(allow_private_networks=False))
    try:
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", int(proxy.url.rsplit(":", 1)[1]))
        writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n\r\n".encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        target.close()
        await target.wait_closed()

    assert response.startswith(b"HTTP/1.1 403 Forbidden")
