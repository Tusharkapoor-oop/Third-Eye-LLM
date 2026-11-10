from __future__ import annotations

import unittest
from starlette.requests import Request
from starlette.responses import HTMLResponse

from weblens.demo import handle_demo_request


class DummyService:
    async def search(self, query: str, max_results: int = 5):
        return {
            "results": [
                {
                    "title": f"Result for {query}",
                    "url": "https://example.org/test",
                    "snippet": "Test snippet content",
                    "provider": "mock",
                    "score": 0.95,
                }
            ]
        }

    async def extract(self, url: str):
        return {
            "title": "Extracted Page",
            "url": url,
            "markdown": "# Heading\n\nContent paragraph.",
        }

    async def deep_research(self, query: str, max_tokens: int = 1000):
        return {
            "report": f"Synthesized research for {query}",
            "sources": ["https://example.org/source1"],
        }


def _make_request(path: str = "/", query_string: bytes = b"", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query_string,
        "headers": headers or [(b"accept", b"text/html"), (b"host", b"localhost:7860")],
    }
    return Request(scope)


async def test_demo_home_render():
    service = DummyService()
    req = _make_request()
    resp = await handle_demo_request(req, service)
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "WebLens" in body
    assert "Server Online" in body
    assert "/mcp" in body


async def test_demo_search_action():
    service = DummyService()
    req = _make_request(query_string=b"action=search&q=python")
    resp = await handle_demo_request(req, service)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "Result for python" in body
    assert "https://example.org/test" in body
    assert "Test snippet content" in body


async def test_demo_extract_action():
    service = DummyService()
    req = _make_request(query_string=b"action=extract&url=https://example.org/doc")
    resp = await handle_demo_request(req, service)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "Extracted Page" in body
    assert "Content paragraph" in body


async def test_demo_research_action():
    service = DummyService()
    req = _make_request(query_string=b"action=research&q=quantum")
    resp = await handle_demo_request(req, service)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "Synthesized research for quantum" in body
    assert "https://example.org/source1" in body


async def test_demo_error_resilience():
    class FailingService:
        async def search(self, q: str, max_results: int = 5):
            raise RuntimeError("upstream timeout")

    req = _make_request(query_string=b"action=search&q=fail")
    resp = await handle_demo_request(req, FailingService())
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "Search failed: upstream timeout" in body


if __name__ == "__main__":
    import asyncio

    async def _main():
        await test_demo_home_render()
        await test_demo_search_action()
        await test_demo_extract_action()
        await test_demo_research_action()
        await test_demo_error_resilience()
        print("ALL 5 DEMO TESTS PASSED")

    asyncio.run(_main())
