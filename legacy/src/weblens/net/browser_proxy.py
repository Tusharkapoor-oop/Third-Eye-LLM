"""Local egress proxy for the optional browser path.

Chromium resolves destinations itself, so request interception alone cannot
close the DNS-rebinding gap: a hostname can resolve to a public address during
the check and a private address when Chromium connects.  This proxy is launched
inside the WebLens process and configured as Chromium's HTTP proxy.  Every
HTTP request and HTTPS ``CONNECT`` tunnel is resolved and validated once by
``DestinationPolicy`` before the proxy opens a TCP connection to that exact IP.
The browser therefore never performs the destination lookup itself.

The proxy only listens on an ephemeral loopback port for the lifetime of the
browser.  It is not a general-purpose proxy and does not authenticate clients;
another local process that can reach the port could use it, subject to the same
destination policy.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Iterable

from ..config import Settings
from ..errors import BlockedURLError
from .ssrf import DestinationPolicy

log = logging.getLogger(__name__)

MAX_HEADER_BYTES = 64 * 1024
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024
_READ_CHUNK = 64 * 1024


class BrowserEgressProxy:
    """A minimal HTTP proxy that pins every upstream connection to a checked IP."""

    def __init__(self, settings: Settings, policy: DestinationPolicy | None = None):
        self.s = settings
        self.policy = policy or DestinationPolicy(settings)
        self._max_body = min(max(settings.max_response_bytes, 0), MAX_REQUEST_BODY_BYTES)
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._url: str | None = None
        self._requests = 0

    @property
    def url(self) -> str:
        if self._url is None:
            raise RuntimeError("browser proxy is not running")
        return self._url

    @property
    def requests(self) -> int:
        """Number of proxy requests accepted for handling (diagnostics only)."""
        return self._requests

    async def start(self) -> str:
        if self._url is not None:
            return self._url
        self._server = await asyncio.start_server(
            self._handle,
            "127.0.0.1",
            0,
            limit=MAX_HEADER_BYTES,
        )
        sock = next(iter(self._server.sockets))
        port = int(sock.getsockname()[1])
        self._url = f"http://127.0.0.1:{port}"
        return self._url

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._url = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._requests += 1
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            method, target, headers = await asyncio.wait_for(self._read_head(reader), self.s.read_timeout_s)
            if method == "CONNECT":
                await self._connect(reader, writer, target)
            else:
                await asyncio.wait_for(
                    self._forward_http(reader, writer, method, target, headers),
                    self.s.total_timeout_s,
                )
        except BlockedURLError:
            await self._send_error(writer, 403, "Forbidden")
        except TimeoutError:
            await self._send_error(writer, 504, "Gateway Timeout")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.debug("browser proxy rejected a request", exc_info=True)
            await self._send_error(writer, 400, "Bad Request")
        finally:
            if task is not None:
                self._tasks.discard(task)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _read_head(self, reader: asyncio.StreamReader) -> tuple[str, str, list[tuple[str, str]]]:
        raw = await reader.readuntil(b"\r\n\r\n")
        if len(raw) > MAX_HEADER_BYTES:
            raise ValueError("request headers too large")
        lines = raw[:-4].split(b"\r\n")
        if not lines or not lines[0]:
            raise ValueError("missing request line")
        try:
            request_line = lines[0].decode("latin-1")
        except UnicodeDecodeError as e:
            raise ValueError("invalid request line") from e
        parts = request_line.split(" ")
        if len(parts) != 3:
            raise ValueError("invalid request line")
        method, target, version = parts
        if not method or not target or version not in {"HTTP/1.1", "HTTP/1.0"}:
            raise ValueError("invalid request line")

        headers: list[tuple[str, str]] = []
        for line in lines[1:]:
            if not line:
                continue
            if b":" not in line:
                raise ValueError("invalid header")
            key_b, value_b = line.split(b":", 1)
            key = key_b.decode("latin-1").strip()
            value = value_b.decode("latin-1").lstrip(" \t")
            if not key or "\x00" in key or "\x00" in value:
                raise ValueError("invalid header")
            headers.append((key, value))
        return method.upper(), target, headers

    async def _connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        target: str,
    ) -> None:
        established = False
        host, port = _split_authority(target)
        upstream: tuple[asyncio.StreamReader, asyncio.StreamWriter] | None = None
        try:
            dest = await self.policy.resolve(host, port)
            upstream = await asyncio.wait_for(
                asyncio.open_connection(dest.ip, port),
                self.s.connect_timeout_s,
            )
            upstream_reader, upstream_writer = upstream
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            established = True
            await self._tunnel(reader, writer, upstream_reader, upstream_writer)
        except BlockedURLError:
            if not established:
                await self._send_error(writer, 403, "Forbidden")
        except TimeoutError:
            if not established:
                await self._send_error(writer, 504, "Gateway Timeout")
        except asyncio.CancelledError:
            raise
        except Exception:
            if not established:
                log.debug("browser proxy CONNECT failed", exc_info=True)
                await self._send_error(writer, 502, "Bad Gateway")
        finally:
            if upstream is not None:
                _, upstream_writer = upstream
                upstream_writer.close()
                with contextlib.suppress(Exception):
                    await upstream_writer.wait_closed()

    async def _forward_http(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        method: str,
        target: str,
        headers: list[tuple[str, str]],
    ) -> None:
        from urllib.parse import urlsplit

        url = urlsplit(target)
        if url.scheme.lower() != "http" or not url.hostname:
            raise ValueError("absolute http URL required")
        if url.username is not None or url.password is not None:
            raise ValueError("userinfo is not allowed in proxy requests")
        if _values(headers, "upgrade"):
            # The forward path is request/response only.  Reject a cleartext
            # WebSocket-style upgrade instead of leaving a half-duplex pipe open.
            raise ValueError("HTTP upgrade is not supported")
        port = url.port or 80
        dest = await self.policy.resolve(url.hostname, port)
        if _expects_continue(headers):
            writer.write(b"HTTP/1.1 100 Continue\r\n\r\n")
            await writer.drain()
        body, chunked = await self._read_body(reader, headers)
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(dest.ip, port),
                self.s.connect_timeout_s,
            )
        except Exception:
            if not writer.is_closing():
                await self._send_error(writer, 502, "Bad Gateway")
            return
        try:
            path = url.path or "/"
            if url.query:
                path = f"{path}?{url.query}"
            out_headers = _request_headers(headers, body, chunked, url.netloc)
            request = (
                f"{method} {path} HTTP/1.1\r\n".encode("latin-1")
                + b"\r\n".join(out_headers)
                + b"\r\n\r\n"
                + (body or b"")
            )
            upstream_writer.write(request)
            await upstream_writer.drain()
            await self._pipe(upstream_reader, writer)
        finally:
            upstream_writer.close()
            with contextlib.suppress(Exception):
                await upstream_writer.wait_closed()

    async def _read_body(
        self, reader: asyncio.StreamReader, headers: list[tuple[str, str]]
    ) -> tuple[bytes | None, bool]:
        transfer = _values(headers, "transfer-encoding")
        lengths = _values(headers, "content-length")
        if transfer:
            if len(transfer) != 1 or transfer[0].lower().strip() != "chunked":
                raise ValueError("unsupported transfer encoding")
            if lengths:
                raise ValueError("both transfer-encoding and content-length present")
            return await self._read_chunked(reader), True
        if not lengths:
            return None, False
        if len(set(lengths)) != 1:
            raise ValueError("conflicting content-length values")
        try:
            length = int(lengths[0])
        except ValueError as e:
            raise ValueError("invalid content-length") from e
        if length < 0 or length > self._max_body:
            raise ValueError("request body too large")
        return await reader.readexactly(length), False

    async def _read_chunked(self, reader: asyncio.StreamReader) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            line = await reader.readuntil(b"\r\n")
            if len(line) > 1024:
                raise ValueError("chunk size line too long")
            try:
                size = int(line[:-2].split(b";", 1)[0], 16)
            except ValueError as e:
                raise ValueError("invalid chunk size") from e
            if size == 0:
                chunks.append(line)
                while True:
                    trailer = await reader.readuntil(b"\r\n")
                    chunks.append(trailer)
                    if trailer == b"\r\n":
                        return b"".join(chunks)
            total += size
            if total > self._max_body:
                raise ValueError("request body too large")
            data = await reader.readexactly(size + 2)
            if not data.endswith(b"\r\n"):
                raise ValueError("invalid chunk terminator")
            chunks.append(line)
            chunks.append(data)

    async def _tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        await asyncio.gather(
            self._pipe(client_reader, upstream_writer),
            self._pipe(upstream_reader, client_writer),
            return_exceptions=True,
        )

    async def _pipe(self, source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> None:
        try:
            while data := await source.read(_READ_CHUNK):
                sink.write(data)
                await sink.drain()
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            with contextlib.suppress(Exception):
                sink.write_eof()

    async def _send_error(self, writer: asyncio.StreamWriter, status: int, reason: str) -> None:
        if writer.is_closing():
            return
        body = f"{status} {reason}\n".encode("ascii")
        response = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii") + body
        with contextlib.suppress(Exception):
            writer.write(response)
            await writer.drain()


def _values(headers: Iterable[tuple[str, str]], name: str) -> list[str]:
    wanted = name.lower()
    return [value for key, value in headers if key.lower() == wanted]


def _expects_continue(headers: Iterable[tuple[str, str]]) -> bool:
    return any(value.strip().lower() == "100-continue" for value in _values(headers, "expect"))


def _split_authority(authority: str) -> tuple[str, int]:
    if authority.startswith("["):
        host, separator, rest = authority.partition("]")
        if not separator or not rest.startswith(":"):
            raise ValueError("invalid CONNECT authority")
        host = host[1:]
        port_text = rest[1:]
    else:
        host, separator, port_text = authority.rpartition(":")
        if not separator or not host:
            raise ValueError("invalid CONNECT authority")
    try:
        port = int(port_text)
    except ValueError as e:
        raise ValueError("invalid CONNECT port") from e
    if not host or not 1 <= port <= 65535:
        raise ValueError("invalid CONNECT authority")
    return host, port


def _request_headers(
    headers: list[tuple[str, str]],
    body: bytes | None,
    chunked: bool,
    authority: str,
) -> list[bytes]:
    out: list[bytes] = [b"Host: " + authority.encode("latin-1")]
    skip = {
        "host",
        "connection",
        "proxy-connection",
        "proxy-authorization",
        "content-length",
        "transfer-encoding",
        "expect",
    }
    for key, value in headers:
        if key.lower() in skip:
            continue
        out.append(f"{key}: {value}".encode("latin-1"))
    if chunked:
        out.append(b"Transfer-Encoding: chunked")
    elif body is not None:
        out.append(b"Content-Length: " + str(len(body)).encode("ascii"))
    out.append(b"Connection: close")
    return out
