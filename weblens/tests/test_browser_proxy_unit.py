"""Unit tests for BrowserEgressProxy edge cases using in-memory fakes.

These tests avoid binding ports and do not require a real upstream server.
"""

from __future__ import annotations

import asyncio

import pytest

from weblens.config import Settings
from weblens.net import browser_proxy as bp
from weblens.net.ssrf import DestinationPolicy


class FakeWriter:
    def __init__(self):
        self.data: list[bytes] = []
        self._closing = False

    def write(self, data: bytes) -> None:
        self.data.append(data)

    async def drain(self) -> None:
        return

    def close(self) -> None:
        self._closing = True

    async def wait_closed(self) -> None:
        return

    def is_closing(self) -> bool:
        return self._closing

    def write_eof(self) -> None:
        self.data.append(b"")


def fake_reader(chunks: list[bytes]) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    for chunk in chunks:
        reader.feed_data(chunk)
    reader.feed_eof()
    return reader


def test_split_authority():
    assert bp._split_authority("example.com:443") == ("example.com", 443)
    assert bp._split_authority("[::1]:8080") == ("::1", 8080)
    with pytest.raises(ValueError):
        bp._split_authority("example.com")
    with pytest.raises(ValueError):
        bp._split_authority("[::1]")
    with pytest.raises(ValueError):
        bp._split_authority("example.com:abc")
    with pytest.raises(ValueError):
        bp._split_authority(":443")
    with pytest.raises(ValueError):
        bp._split_authority("example.com:0")


def test_values_and_expects_continue():
    headers = [("Expect", "100-continue"), ("Content-Length", "5"), ("expect", "100-continue")]
    assert bp._values(headers, "expect") == ["100-continue", "100-continue"]
    assert bp._expects_continue(headers) is True
    assert bp._values([("X", "1")], "expect") == []
    assert bp._expects_continue([("X", "1")]) is False


def test_request_headers_rewrites_and_skips():
    headers = [
        ("Host", "original"),
        ("Connection", "keep-alive"),
        ("Proxy-Connection", "keep-alive"),
        ("Proxy-Authorization", "Basic x"),
        ("Content-Length", "5"),
        ("Transfer-Encoding", "chunked"),
        ("Expect", "100-continue"),
        ("X-Custom", "value"),
    ]
    out = bp._request_headers(headers, b"hello", False, "example.com")
    out_str = [line.decode("latin-1") for line in out]
    assert "Host: example.com" in out_str
    assert "X-Custom: value" in out_str
    assert "Content-Length: 5" in out_str
    assert all(
        skip not in out_str
        for skip in (
            "Connection: keep-alive",
            "Proxy-Connection: keep-alive",
            "Proxy-Authorization: Basic x",
            "Transfer-Encoding: chunked",
            "Expect: 100-continue",
        )
    )
    assert "Connection: close" in out_str


def test_request_headers_chunked_body():
    headers = [("Host", "example.com"), ("Content-Length", "5")]
    out = bp._request_headers(headers, b"hello", True, "example.com")
    out_str = [line.decode("latin-1") for line in out]
    assert "Transfer-Encoding: chunked" in out_str
    assert not any(line.startswith("Content-Length:") for line in out_str)


@pytest.mark.asyncio
async def test_send_error_when_writer_closing():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    writer = FakeWriter()
    writer.close()
    await proxy._send_error(writer, 403, "Forbidden")
    assert len([d for d in writer.data if d]) == 0


@pytest.mark.asyncio
async def test_send_error_writes_response():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    writer = FakeWriter()
    await proxy._send_error(writer, 403, "Forbidden")
    response = b"".join(writer.data)
    assert response.startswith(b"HTTP/1.1 403 Forbidden")
    assert b"Content-Length: 14" in response


@pytest.mark.asyncio
async def test_read_head_rejects_invalid_request_line():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    for bad in [b"garbage\r\n\r\n", b"GET\r\n\r\n", b"GET / HTTP/2.0\r\n\r\n", b"GET / HTTP/1.1\r\nno-colon\r\n\r\n"]:
        reader = asyncio.StreamReader()
        reader.feed_data(bad)
        reader.feed_eof()
        with pytest.raises((ValueError, asyncio.IncompleteReadError)):
            await proxy._read_head(reader)


@pytest.mark.asyncio
async def test_read_body_content_length():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    reader = asyncio.StreamReader()
    reader.feed_data(b"hello world")
    reader.feed_eof()
    body, chunked = await proxy._read_body(reader, [("Content-Length", "5")])
    assert body == b"hello"
    assert chunked is False


@pytest.mark.asyncio
async def test_read_body_too_large():
    s = Settings(allow_private_networks=True, max_response_bytes=4)
    proxy = bp.BrowserEgressProxy(s)
    reader = asyncio.StreamReader()
    reader.feed_data(b"hello world")
    reader.feed_eof()
    with pytest.raises(ValueError):
        await proxy._read_body(reader, [("Content-Length", "11")])


@pytest.mark.asyncio
async def test_read_body_unsupported_transfer_encoding():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    reader = asyncio.StreamReader()
    reader.feed_eof()
    with pytest.raises(ValueError):
        await proxy._read_body(reader, [("Transfer-Encoding", "gzip")])


@pytest.mark.asyncio
async def test_read_body_conflicting_lengths():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    reader = asyncio.StreamReader()
    reader.feed_eof()
    with pytest.raises(ValueError):
        await proxy._read_body(reader, [("Content-Length", "5"), ("Content-Length", "6")])


@pytest.mark.asyncio
async def test_read_body_both_chunked_and_length():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    reader = asyncio.StreamReader()
    reader.feed_eof()
    with pytest.raises(ValueError):
        await proxy._read_body(reader, [("Transfer-Encoding", "chunked"), ("Content-Length", "5")])


@pytest.mark.asyncio
async def test_read_chunked_full():
    """_read_chunked must re-frame the whole body, not just return the prefix.

    The previous assertion (``out.startswith`` the raw input) passes for an
    implementation that does no chunked parsing at all. This asserts the exact
    re-framed bytes for a multi-chunk body plus the terminating chunk.
    """
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    raw = b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()
    out = await proxy._read_chunked(reader)
    # Every chunk is preserved in order, and the zero chunk closes the body.
    assert out == raw
    assert out.count(b"\r\n") == raw.count(b"\r\n")


@pytest.mark.asyncio
async def test_read_chunked_rejects_oversized_body():
    """The size cap must actually fire; a no-op reader would return the data."""
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    proxy._max_body = 4  # anything larger than this must be refused
    reader = asyncio.StreamReader()
    reader.feed_data(b"10\r\n0123456789abcdef\r\n0\r\n\r\n")
    reader.feed_eof()
    with pytest.raises(ValueError):
        await proxy._read_chunked(reader)


@pytest.mark.asyncio
async def test_read_chunked_bad_size_line():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    reader = asyncio.StreamReader()
    reader.feed_data(b"x\r\n")
    reader.feed_eof()
    with pytest.raises(ValueError):
        await proxy._read_chunked(reader)


@pytest.mark.asyncio
async def test_read_chunked_missing_terminator():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    reader = asyncio.StreamReader()
    reader.feed_data(b"5\r\nhello\r\n")
    reader.feed_eof()
    with pytest.raises(asyncio.IncompleteReadError):
        await proxy._read_chunked(reader)


@pytest.mark.asyncio
async def test_handle_blocks_url(monkeypatch):
    policy = DestinationPolicy(Settings(allow_private_networks=False))
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=False), policy=policy)
    await proxy.start()
    try:
        port = int(proxy.url.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(f"GET http://127.0.0.1:{port}/ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
        assert response.startswith(b"HTTP/1.1 403 Forbidden")
    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_handle_bad_request(monkeypatch):
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    await proxy.start()
    try:
        port = int(proxy.url.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"garbage\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
        assert response.startswith(b"HTTP/1.1 400 Bad Request")
    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_handle_timeout_on_read(monkeypatch):
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True, read_timeout_s=0.001))
    await proxy.start()
    try:
        port = int(proxy.url.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # Do not send anything so readuntil times out.
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        await writer.wait_closed()
        assert response.startswith(b"HTTP/1.1 504 Gateway Timeout")
    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_forward_http_http_required():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    await proxy.start()
    try:
        port = int(proxy.url.rsplit(":", 1)[1])
        for target in ("ftp://example.com/file", "http://evil:user@example.com/"):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(f"GET {target} HTTP/1.1\r\nHost: example.com\r\n\r\n".encode())
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 5)
            writer.close()
            await writer.wait_closed()
            assert response.startswith(b"HTTP/1.1 400")
    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_close_cancels_pending_tasks():
    proxy = bp.BrowserEgressProxy(Settings(allow_private_networks=True))
    await proxy.start()
    task = asyncio.create_task(asyncio.sleep(10))
    proxy._tasks.add(task)
    await proxy.close()
    assert task.cancelled() or task.done()
    assert proxy._url is None
