"""Strict unit tests for the Qwen / Gemma provider routes and model readiness.

All network access is mocked at the HTTP seam the client actually uses
(``MultiModelClient._post_nvidia_with_retry``), so these tests are offline and
deterministic.
"""

from __future__ import annotations

import json

import httpx
import pytest

from model_provider import ModelProvider, MultiModelClient


def _ok_response(model: str, content: str = "PONG") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        },
        request=httpx.Request("POST", "https://gateway.test/v1/chat/completions"),
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> MultiModelClient:
    c = MultiModelClient()
    monkeypatch.setattr(c, "nvidia_mistral_key", "")
    monkeypatch.setattr(c, "nvidia_gpt_key", "")
    monkeypatch.setattr(c, "gemini_key", "")
    return c


def test_model_family_classification(client: MultiModelClient) -> None:
    assert client.model_family("qwen/qwen3-235b-a22b-instruct") is ModelProvider.QWEN
    assert client.model_family("Qwen/Qwen2.5-72B") is ModelProvider.QWEN
    assert client.model_family("google/gemma-4-31b-it") is ModelProvider.GEMMA
    assert client.model_family("gemini-3.5-flash") is ModelProvider.GEMINI
    assert client.model_family("mistralai/mistral-large-4-1t-a52b") is ModelProvider.NVIDIA


def test_readiness_requires_key_and_gateway(client: MultiModelClient) -> None:
    reported = client.model_readiness()
    assert reported["qwen"]["ready"] is False
    assert "QWEN_API_KEY" in reported["qwen"]["blocked_reason"]

    client.qwen_key = "sk-test"
    assert client.model_readiness()["qwen"]["ready"] is False  # gateway url still missing

    client.qwen_base_url = "https://gateway.test/v1"
    assert client.model_readiness()["qwen"]["ready"] is True
    assert client.model_readiness()["qwen"]["blocked_reason"] is None


@pytest.mark.asyncio
async def test_qwen_routes_to_gateway_with_its_own_key(
    client: MultiModelClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.qwen_key = "sk-qwen"
    client.qwen_base_url = "https://gateway.test/v1"
    seen: dict[str, object] = {}

    async def fake_post(endpoint, payload, api_key, timeout=15.0, max_retries=1, base_url=None):
        seen.update(endpoint=endpoint, payload=payload, api_key=api_key, base_url=base_url)
        return _ok_response("qwen/qwen3-235b-a22b-instruct")

    monkeypatch.setattr(client, "_post_nvidia_with_retry", fake_post)

    res = await client.generate(prompt="Reply with exactly: PONG", model="qwen/qwen3-235b-a22b-instruct")

    assert res.provider is ModelProvider.QWEN
    assert res.model_name == "qwen/qwen3-235b-a22b-instruct"
    assert res.content == "PONG"
    assert res.prompt_tokens == 7 and res.completion_tokens == 2
    assert seen["base_url"] == "https://gateway.test/v1"
    assert seen["api_key"] == "sk-qwen"
    assert seen["endpoint"] == "/chat/completions"
    assert seen["payload"]["model"] == "qwen/qwen3-235b-a22b-instruct"


@pytest.mark.asyncio
async def test_qwen_without_gateway_never_claims_to_be_qwen(
    client: MultiModelClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unconfigured Qwen must fall back and say so in provider/model fields."""
    calls: list[str] = []

    async def fake_post(endpoint, payload, api_key, timeout=15.0, max_retries=1, base_url=None):
        calls.append(base_url or "")
        return httpx.Response(403, json={"detail": "Forbidden"}, request=httpx.Request("POST", "https://x"))

    monkeypatch.setattr(client, "_post_nvidia_with_retry", fake_post)

    res = await client.generate(prompt="hi", model="qwen/qwen3-235b-a22b-instruct")

    assert res.provider is ModelProvider.LOCAL_ALGORITHMIC
    assert res.model_name != "qwen/qwen3-235b-a22b-instruct"
    assert calls == []  # no key: never even attempted


@pytest.mark.asyncio
async def test_gemma_uses_gemma_host_and_skips_generic_nvidia_route(
    client: MultiModelClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.gemma_key = "nv-gemma"
    client.gemma_base_url = "https://gemma.test/v1"
    client.nvidia_mistral_key = "nv-should-not-be-used"
    seen: list[tuple[str, str | None]] = []

    async def fake_post(endpoint, payload, api_key, timeout=15.0, max_retries=1, base_url=None):
        seen.append((api_key, base_url))
        return _ok_response(payload["model"], "OK")

    monkeypatch.setattr(client, "_post_nvidia_with_retry", fake_post)

    res = await client.generate(prompt="hi", model="google/gemma-4-31b-it")

    assert res.provider is ModelProvider.GEMMA
    assert res.model_name == "google/gemma-4-31b-it"
    # exactly one attempt: the Gemma host, never the generic NVIDIA route
    assert seen == [("nv-gemma", "https://gemma.test/v1")]


@pytest.mark.asyncio
async def test_gemma_403_falls_back_but_reports_real_provider(
    client: MultiModelClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.gemma_key = "nv-gemma"
    client.nvidia_mistral_key = "nv-mistral"

    async def fake_post(endpoint, payload, api_key, timeout=15.0, max_retries=1, base_url=None):
        return httpx.Response(403, json={"detail": "Forbidden"}, request=httpx.Request("POST", "https://x"))

    monkeypatch.setattr(client, "_post_nvidia_with_retry", fake_post)

    res = await client.generate(prompt="hi", model="google/gemma-4-31b-it")

    # No silent impersonation: the caller can see Gemma was never served.
    assert res.provider is ModelProvider.LOCAL_ALGORITHMIC
    assert res.model_name != "google/gemma-4-31b-it"


def test_research_fallback_emits_no_malformed_url(client: MultiModelClient) -> None:
    """The deterministic fallback must not print 'https://...…' as link text."""
    import asyncio

    sources = [
        {"title": "Alpha", "url": "https://alpha.example.org/report-2026", "content": "42 units."},
    ]

    async def fake_generate(**kwargs):
        from model_provider import ModelResult

        return ModelResult(
            content="",  # forces deterministic fallback
            reasoning_content=None,
            model_name="algorithmic-deterministic",
            provider=ModelProvider.LOCAL_ALGORITHMIC,
            prompt_tokens=1,
            completion_tokens=0,
            latency_ms=1.0,
        )

    client.generate = fake_generate  # type: ignore[method-assign]
    res = asyncio.run(
        client.synthesize_research_report(prompt="p", sources=sources, model="gemini-3.5-flash")
    )

    assert "https://alpha.example.org/report-2026" in res.content
    assert "…" not in res.content
    assert "report-2026..." not in res.content
    # every URL-looking token in the output is a real source URL
    import re

    urls = re.findall(r"https?://[^\s)\]>\"']+", res.content)
    assert urls and all(u == "https://alpha.example.org/report-2026" for u in urls)
    json.dumps(res.content)  # serialisable envelope
