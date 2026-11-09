"""Empirical verification suite for cascading model fallback and resilience.

Verifies:
1. Cascading model fallback: Tier 1 NVIDIA NIM -> Tier 2 Gemini -> Tier 3 Local Algorithmic Synthesizer.
2. Resilience against HTTP 404, HTTP 429, and HTTP Timeout from upstream endpoints.
3. Preservation and extraction of reasoning tokens without empty content drops.
4. Deterministic Tier 3 grounded research report generation with verified citations and markdown tables.
5. Task-specific routing logic across model tiers.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
import httpx
import pytest
import respx

from model_provider import ModelProvider, ModelResult, MultiModelClient


@pytest.fixture
def client() -> MultiModelClient:
    return MultiModelClient()


@pytest.mark.asyncio
async def test_nvidia_200_success_with_reasoning(client: MultiModelClient):
    """Verify Tier 1 NVIDIA NIM successfully extracts content and reasoning tokens."""
    fake_response = {
        "id": "chat-test-123",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"result": "success"}',
                    "reasoning_content": "Chain of thought deliberation here.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 120,
            "total_tokens": 170,
        },
    }

    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as respx_mock:
        respx_mock.post("/chat/completions").respond(status_code=200, json=fake_response)

        res = await client.generate(
            prompt="Test prompt",
            model="mistralai/mistral-large-4-1t-a52b",
        )

        assert res.provider == ModelProvider.NVIDIA
        assert res.model_name == "mistralai/mistral-large-4-1t-a52b"
        assert res.content == '{"result": "success"}'
        assert res.reasoning_content == "Chain of thought deliberation here."
        assert res.prompt_tokens == 50
        assert res.completion_tokens == 120
        assert res.latency_ms > 0.0


@pytest.mark.asyncio
async def test_nvidia_empty_content_reasoning_fallback(client: MultiModelClient):
    """Verify when content is blank but reasoning_content exists, reasoning is preserved as content."""
    fake_response = {
        "id": "chat-test-empty",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "All tokens were spent in reasoning deliberation.",
                },
                "finish_reason": "length",
            }
        ],
        "usage": {
            "prompt_tokens": 30,
            "completion_tokens": 80,
            "total_tokens": 110,
        },
    }

    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as respx_mock:
        respx_mock.post("/chat/completions").respond(status_code=200, json=fake_response)

        res = await client.generate(
            prompt="Reasoning prompt",
            model="mistralai/mistral-large-4-1t-a52b",
        )

        assert res.provider == ModelProvider.NVIDIA
        assert res.content == "All tokens were spent in reasoning deliberation."
        assert res.reasoning_content == "All tokens were spent in reasoning deliberation."


@pytest.mark.asyncio
async def test_nvidia_404_failover_to_gemini(client: MultiModelClient):
    """Verify HTTP 404 from NVIDIA NIM falls through to Tier 2 Gemini without unhandled crash."""
    mock_gemini_resp = MagicMock()
    mock_gemini_resp.text = "Gemini synthesized answer following NVIDIA 404"

    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as respx_mock:
        respx_mock.post("/chat/completions").respond(
            status_code=404,
            json={"error": "Function not found for account"},
        )

        with patch("google.genai.Client") as mock_genai_cls:
            mock_genai_inst = MagicMock()
            mock_genai_cls.return_value = mock_genai_inst
            mock_genai_inst.models.generate_content.return_value = mock_gemini_resp

            # Set a fake gemini key to guarantee Tier 2 triggers
            original_gemini_key = client.gemini_key
            client.gemini_key = "fake_gemini_key_for_test"
            try:
                res = await client.generate(
                    prompt="Summarize topic",
                    model="nv-mistralai/mistral-nemo-12b-instruct",
                )
                assert res.provider == ModelProvider.GEMINI
                assert "gemini" in res.model_name
                assert res.content == "Gemini synthesized answer following NVIDIA 404"
            finally:
                client.gemini_key = original_gemini_key


@pytest.mark.asyncio
async def test_nvidia_429_failover_to_gemini(client: MultiModelClient):
    """Verify HTTP 429 (Rate Limit / Quota) from NVIDIA NIM falls through to Tier 2 Gemini without crash."""
    mock_gemini_resp = MagicMock()
    mock_gemini_resp.text = "Gemini answer after Tier 1 rate limit"

    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as respx_mock:
        respx_mock.post("/chat/completions").respond(
            status_code=429,
            json={"error": "Rate limit exceeded. Please throttle requests."},
        )

        with patch("google.genai.Client") as mock_genai_cls:
            mock_genai_inst = MagicMock()
            mock_genai_cls.return_value = mock_genai_inst
            mock_genai_inst.models.generate_content.return_value = mock_gemini_resp

            original_gemini_key = client.gemini_key
            client.gemini_key = "fake_gemini_key_for_test"
            try:
                res = await client.generate(
                    prompt="Rate limit test",
                    model="mistralai/mistral-large-4-1t-a52b",
                )
                assert res.provider == ModelProvider.GEMINI
                assert res.content == "Gemini answer after Tier 1 rate limit"
            finally:
                client.gemini_key = original_gemini_key


@pytest.mark.asyncio
async def test_nvidia_timeout_failover_to_gemini(client: MultiModelClient):
    """Verify upstream ReadTimeout from NVIDIA NIM retries and cascades to Tier 2 without crashing."""
    mock_gemini_resp = MagicMock()
    mock_gemini_resp.text = "Gemini answer after Tier 1 timeout"

    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            side_effect=httpx.ReadTimeout("NVIDIA upstream model took > 18s")
        )

        with patch("google.genai.Client") as mock_genai_cls:
            mock_genai_inst = MagicMock()
            mock_genai_cls.return_value = mock_genai_inst
            mock_genai_inst.models.generate_content.return_value = mock_gemini_resp

            original_gemini_key = client.gemini_key
            client.gemini_key = "fake_gemini_key_for_test"
            try:
                res = await client.generate(
                    prompt="Timeout test prompt",
                    model="openai/gpt-oss-20b",
                )
                assert res.provider == ModelProvider.GEMINI
                assert res.content == "Gemini answer after Tier 1 timeout"
            finally:
                client.gemini_key = original_gemini_key


@pytest.mark.asyncio
async def test_full_cascade_to_tier3_algorithmic(client: MultiModelClient):
    """Verify that when both Tier 1 (NVIDIA) and Tier 2 (Gemini) fail, Tier 3 succeeds deterministically."""
    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as respx_mock:
        # Tier 1 fails with 500
        respx_mock.post("/chat/completions").respond(status_code=500, text="Internal Server Error")

        # Tier 2 fails with 429 Quota Exhausted on all Gemini models
        with patch("google.genai.Client") as mock_genai_cls:
            mock_genai_inst = MagicMock()
            mock_genai_cls.return_value = mock_genai_inst
            mock_genai_inst.models.generate_content.side_effect = RuntimeError("ResourceExhausted 429 quota")

            original_gemini_key = client.gemini_key
            client.gemini_key = "fake_gemini_key_for_test"
            try:
                res = await client.generate(
                    prompt="Synthesize quantum computing state",
                    model="mistralai/mistral-large-4-1t-a52b",
                )
                assert res.provider == ModelProvider.LOCAL_ALGORITHMIC
                assert res.model_name == "algorithmic-deterministic"
                assert "Synthesized evidence for: Synthesize quantum computing state" in res.content
                assert res.latency_ms > 0.0
            finally:
                client.gemini_key = original_gemini_key


@pytest.mark.asyncio
async def test_synthesize_research_report_tier3_structure(client: MultiModelClient):
    """Verify synthesize_research_report formats complete markdown brief with citations and table on Tier 3 fallback."""
    sources = [
        {
            "title": "NVIDIA Architecture Brief",
            "url": "https://developer.nvidia.com/nim",
            "content": "NVIDIA NIM microservices provide optimized inference containers across leading open models.",
        },
        {
            "title": "Google DeepMind Gemini Report",
            "url": "https://deepmind.google/technologies/gemini",
            "content": "Gemini models feature multimodal capabilities and long context window token processing.",
        },
    ]

    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as respx_mock:
        # Simulate endpoint 404
        respx_mock.post("/chat/completions").respond(status_code=404, text="Endpoint unmapped")

        # Ensure Gemini is bypassed or disabled
        original_gemini_key = client.gemini_key
        client.gemini_key = ""
        try:
            report_result = await client.synthesize_research_report(
                prompt="Model Orchestration Architecture",
                sources=sources,
                mode="pro",
            )

            assert report_result.provider == ModelProvider.LOCAL_ALGORITHMIC
            report = report_result.content

            # Verify Executive Summary
            assert "# Web Intelligence Research Report: Model Orchestration Architecture" in report
            assert "## Executive Summary" in report
            assert "verified web evidence retrieved across 2 authoritative sources" in report

            # Verify Key Findings & Citations
            assert "## Key Findings & Verified Evidence" in report
            assert "### [NVIDIA Architecture Brief](https://developer.nvidia.com/nim)" in report
            assert "> NVIDIA NIM microservices provide optimized inference containers" in report
            assert "*Verified Reference: [NVIDIA Architecture Brief](https://developer.nvidia.com/nim)*" in report

            # Verify Evidence Summary Table
            assert "## Evidence Summary & Sources Table" in report
            assert "| Source Title | Canonical URL | Verification |" in report
            assert "| NVIDIA Architecture Brief |" in report
            assert "| Google DeepMind Gemini Report |" in report
            assert (
                "| NVIDIA Architecture Brief | "
                "[link](https://developer.nvidia.com/nim) | Grounded |"
            ) in report
            assert "| Grounded |" in report

            # Verify footer
            assert "*Synthesized via Autonomous WebLens Engine (pro mode) across 2 sources.*" in report
        finally:
            client.gemini_key = original_gemini_key


def test_route_model_rules(client: MultiModelClient):
    """Verify route_model assigns optimal models to task domains."""
    assert client.route_model("deep_research") == "mistralai/mistral-large-4-1t-a52b"
    assert client.route_model("financial_analysis") == "mistralai/mistral-large-4-1t-a52b"
    assert client.route_model("compliance_screening") == "mistralai/mistral-large-4-1t-a52b"

    assert client.route_model("data_enrichment") == "openai/gpt-oss-20b"
    assert client.route_model("reasoning_audit") == "openai/gpt-oss-20b"
    assert client.route_model("company_research") == "openai/gpt-oss-20b"

    assert client.route_model("quick_search") == "nv-mistralai/mistral-nemo-12b-instruct"
    assert client.route_model("query_rewrite") == "nv-mistralai/mistral-nemo-12b-instruct"

    # Default fallback
    assert client.route_model("unrecognized_task") == "mistralai/mistral-large-4-1t-a52b"
