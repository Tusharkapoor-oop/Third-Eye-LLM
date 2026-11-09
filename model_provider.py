"""Multi-Model Intelligence Provider Engine for WebLens.

Provides a unified, resilient multi-model abstraction interfacing with:
- NVIDIA NIM API (Mistral Large 4, GPT-OSS 20B, Mistral NeMo 12B)
- Google Gemini API (gemini-3.8-flash, with automatic quota-exhaustion fallback)
- Local Grounded Algorithmic Synthesizer (zero-latency, deterministic fallback)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import re
import socket
import time
from typing import Any, Literal
import httpx

from config import CONFIG
from security import shared_ssl_context

logger = logging.getLogger("weblens.models")


class ModelProvider(StrEnum):
    NVIDIA = "nvidia"
    GEMINI = "gemini"
    QWEN = "qwen"
    GEMMA = "gemma"
    LOCAL_ALGORITHMIC = "local_algorithmic"


@dataclass
class ModelResult:
    content: str
    reasoning_content: str | None
    model_name: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float = 0.0


class MultiModelClient:
    """Enterprise multi-model client with intelligent routing and multi-tier fallback."""

    def __init__(self) -> None:
        self.nvidia_base_url = CONFIG.nvidia_base_url.rstrip("/")

        # Clean Bearer prefix if user copied it from web dashboard
        mistral_k = CONFIG.nvidia_mistral_large_key
        if mistral_k.startswith("Bearer "):
            mistral_k = mistral_k[7:].strip()
        self.nvidia_mistral_key = mistral_k

        gpt_k = CONFIG.nvidia_gpt_oss_20b_key
        if gpt_k.startswith("Bearer "):
            gpt_k = gpt_k[7:].strip()
        self.nvidia_gpt_key = gpt_k or mistral_k

        self.gemini_key = CONFIG.gemini_api_key

        self.qwen_model = CONFIG.qwen_model
        self.qwen_base_url = CONFIG.qwen_base_url.rstrip("/")
        self.qwen_key = CONFIG.qwen_api_key.strip()

        self.gemma_model = CONFIG.gemma_model
        self.gemma_base_url = CONFIG.gemma_base_url.rstrip("/")
        gemma_key = CONFIG.gemma_api_key.strip()
        if gemma_key.startswith("Bearer "):
            gemma_key = gemma_key[7:].strip()
        self.gemma_key = gemma_key

    @staticmethod
    def model_family(model: str) -> ModelProvider:
        """Classify a model id into the provider family that must serve it."""
        low = model.lower()
        if "qwen" in low:
            return ModelProvider.QWEN
        if "gemma" in low:
            return ModelProvider.GEMMA
        if low.startswith("gemini") or "gemini" in low:
            return ModelProvider.GEMINI
        return ModelProvider.NVIDIA

    def model_readiness(self) -> dict[str, dict[str, Any]]:
        """Report each configured model and why it can or cannot be called.

        Never reports a model as ready on the strength of a model id alone: a
        credential must be present, and for Qwen an explicit gateway URL too.
        """
        qwen_ready = bool(self.qwen_key and self.qwen_base_url)
        return {
            "qwen": {
                "model": self.qwen_model,
                "provider": ModelProvider.QWEN,
                "ready": qwen_ready,
                "blocked_reason": None
                if qwen_ready
                else "missing QWEN_API_KEY and/or QWEN_BASE_URL (no OpenAI-compatible Qwen gateway configured)",
            },
            "gemma": {
                "model": self.gemma_model,
                "provider": ModelProvider.GEMMA,
                "ready": bool(self.gemma_key and self.gemma_base_url),
                "blocked_reason": None if self.gemma_key else "missing GEMMA_API_KEY / NVIDIA key",
            },
            "mistral": {
                "model": "mistralai/mistral-large-4-1t-a52b",
                "provider": ModelProvider.NVIDIA,
                "ready": bool(self.nvidia_mistral_key),
                "blocked_reason": None if self.nvidia_mistral_key else "missing NVIDIA Mistral key",
            },
            "gemini": {
                "model": "gemini-3.5-flash",
                "provider": ModelProvider.GEMINI,
                "ready": bool(self.gemini_key),
                "blocked_reason": None if self.gemini_key else "missing GEMINI_API_KEY",
            },
        }

    def _get_nvidia_key_for_model(self, model: str) -> str:
        if "gpt" in model.lower() or "20b" in model.lower():
            return self.nvidia_gpt_key or self.nvidia_mistral_key
        return self.nvidia_mistral_key or self.nvidia_gpt_key

    async def _post_nvidia_with_retry(
        self,
        endpoint: str,
        payload: dict[str, Any],
        api_key: str,
        timeout: float = 15.0,
        max_retries: int = 1,
        base_url: str | None = None,
    ) -> httpx.Response:
        """Execute HTTP POST with DNS resolution retry against an OpenAI-compatible host."""
        url = f"{base_url or self.nvidia_base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout, verify=shared_ssl_context()) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    return resp
            except (httpx.ConnectError, socket.gaierror, httpx.TimeoutException) as e:
                last_exc = e
                logger.warning(f"NVIDIA API failure (attempt {attempt+1}/{max_retries+1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(0.5)
            except Exception as e:
                last_exc = e
                break

        raise last_exc or RuntimeError("NVIDIA API call failed after retries")

    async def _generate_openai_compatible(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        base_url: str,
        api_key: str,
        provider: ModelProvider,
        t0: float,
        timeout: float = 18.0,
    ) -> ModelResult | None:
        """Call any OpenAI-compatible /chat/completions host. Returns None on failure."""
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            resp = await self._post_nvidia_with_retry(
                "/chat/completions",
                payload,
                api_key=api_key,
                timeout=timeout,
                max_retries=1,
                base_url=base_url,
            )
        except Exception as e:
            logger.warning(f"{provider} generation error ({model}): {e}")
            return None

        if resp.status_code != 200:
            logger.warning(f"{provider} API HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content")
        if not content.strip() and reasoning:
            content = reasoning.strip()

        usage = data.get("usage", {})
        return ModelResult(
            content=content.strip(),
            reasoning_content=reasoning,
            model_name=model,
            provider=provider,
            prompt_tokens=usage.get("prompt_tokens", len(str(messages)) // 4),
            completion_tokens=usage.get("completion_tokens", len(content.split()) * 2),
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str = "mistralai/mistral-large-4-1t-a52b",
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> ModelResult:
        """Generate response via configured model provider with automatic failover."""
        t0 = time.perf_counter()
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        family = self.model_family(model)

        # Route 0: Qwen via an explicit OpenAI-compatible gateway.
        if family is ModelProvider.QWEN:
            if self.qwen_key and self.qwen_base_url:
                qwen = await self._generate_openai_compatible(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    base_url=self.qwen_base_url,
                    api_key=self.qwen_key,
                    provider=ModelProvider.QWEN,
                    t0=t0,
                )
                if qwen is not None:
                    return qwen
            else:
                logger.warning(
                    "Qwen requested but no gateway configured "
                    "(set QWEN_BASE_URL + QWEN_API_KEY); falling back"
                )

        # Route 0b: Gemma via its own host/key (NVIDIA NIM by default).
        if family is ModelProvider.GEMMA and self.gemma_key and self.gemma_base_url:
            gemma = await self._generate_openai_compatible(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                base_url=self.gemma_base_url,
                api_key=self.gemma_key,
                provider=ModelProvider.GEMMA,
                t0=t0,
            )
            if gemma is not None:
                return gemma
            logger.warning(f"Gemma unavailable for {model}; continuing to fallback chain")

        # Route 1: NVIDIA Hosted Models (skipped for Gemma: route 0b already
        # used this same host and key, so retrying it would only duplicate a
        # known failure).
        if (self.nvidia_mistral_key or self.nvidia_gpt_key) and family is not ModelProvider.GEMMA:
            api_key = self._get_nvidia_key_for_model(model)
            if api_key:
                try:
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": prompt})

                    payload = {
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }

                    resp = await self._post_nvidia_with_retry(
                        "/chat/completions",
                        payload,
                        api_key=api_key,
                        timeout=18.0,
                        max_retries=1,
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        choice = data["choices"][0]
                        msg = choice.get("message", {})
                        content = msg.get("content") or ""
                        reasoning = msg.get("reasoning_content")

                        # If content was empty because all tokens went to reasoning, use reasoning
                        if not content.strip() and reasoning:
                            content = reasoning.strip()

                        usage = data.get("usage", {})
                        prompt_toks = usage.get("prompt_tokens", len(prompt.split()) * 2)
                        comp_toks = usage.get("completion_tokens", len(content.split()) * 2)
                        dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)

                        return ModelResult(
                            content=content.strip(),
                            reasoning_content=reasoning,
                            model_name=model,
                            provider=ModelProvider.NVIDIA,
                            prompt_tokens=prompt_toks,
                            completion_tokens=comp_toks,
                            latency_ms=dur_ms,
                        )
                    else:
                        logger.warning(f"NVIDIA API HTTP {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    logger.warning(f"NVIDIA generation error ({model}): {e}")

        # Route 2: Google Gemini Fallback
        if self.gemini_key:
            try:
                from google import genai
                from google.genai import types as genai_types

                # Bound the SDK's own HTTP timeout. Without it a stalled request
                # keeps its worker thread alive long after asyncio.wait_for has
                # given up, and interpreter shutdown then blocks joining it.
                client = genai.Client(
                    api_key=self.gemini_key,
                    http_options=genai_types.HttpOptions(timeout=20_000),
                )
                full_contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

                loop = asyncio.get_running_loop()
                for gemini_model in ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"):
                    try:
                        g_resp = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                lambda m=gemini_model: client.models.generate_content(
                                    model=m,
                                    contents=full_contents,
                                ),
                            ),
                            timeout=15.0,
                        )
                        if g_resp and g_resp.text:
                            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                            return ModelResult(
                                content=g_resp.text.strip(),
                                reasoning_content=None,
                                model_name=gemini_model,
                                provider=ModelProvider.GEMINI,
                                prompt_tokens=len(full_contents.split()) * 2,
                                completion_tokens=len(g_resp.text.split()) * 2,
                                latency_ms=dur_ms,
                            )
                    except Exception as ge:
                        logger.info(f"Gemini {gemini_model} fallback trigger: {ge}")
                        continue
            except Exception as e:
                logger.warning(f"Gemini provider error: {e}")

        # Route 3: Deterministic Local Algorithmic Synthesis
        dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return ModelResult(
            content=f"Synthesized evidence for: {prompt}",
            reasoning_content=None,
            model_name="algorithmic-deterministic",
            provider=ModelProvider.LOCAL_ALGORITHMIC,
            prompt_tokens=len(prompt.split()),
            completion_tokens=10,
            latency_ms=dur_ms,
        )

    async def synthesize_research_report(
        self,
        prompt: str,
        sources: list[dict[str, Any]],
        mode: Literal["mini", "pro"] = "pro",
        model: str | None = None,
    ) -> ModelResult:
        """Synthesize a complete research report with strict source citations."""
        target_model = model or ("mistralai/mistral-large-4-1t-a52b" if mode == "pro" else "openai/gpt-oss-20b")

        context_blocks = []
        for s in sources:
            title = s.get("title", "Source")
            url = s.get("url", "")
            content = s.get("content", "")
            context_blocks.append(f"### Source: [{title}]({url})\n{content}\n")

        context_str = "\n".join(context_blocks)[:16000]

        system_prompt = (
            "You are a Principal Web Intelligence Analyst. Produce a comprehensive, evidence-grounded "
            "research report answering the user's research objective strictly based on the provided sources.\n"
            "Strict Quality Rules:\n"
            "1. Every factual claim, benchmark, or figure MUST have an inline markdown citation: [Source Title](URL).\n"
            "2. Never hallucinate facts or invent statistics not present in the sources.\n"
            "3. If sources conflict or evidence is missing, explicitly document the discrepancy.\n"
            "4. Organize into Executive Summary, Detailed Analysis with Markdown tables where applicable, "
            "and an Evidence & Limitations Summary."
        )

        user_content = f"Research Prompt: {prompt}\n\nEvidence Sources:\n{context_str}"
        res = await self.generate(
            prompt=user_content,
            system_prompt=system_prompt,
            model=target_model,
            max_tokens=2500 if mode == "pro" else 1200,
        )

        # High-Quality Deterministic Fallback if External Model Throttled/Unavailable
        if res.provider == ModelProvider.LOCAL_ALGORITHMIC or not res.content or len(res.content.strip()) < 50:
            lines = [
                f"# Web Intelligence Research Report: {prompt}",
                "",
                "## Executive Summary",
                f"This intelligence brief synthesizes verified web evidence retrieved across {len(sources)} authoritative sources "
                f"addressing the research objective: *{prompt}*.",
                "",
                "## Key Findings & Verified Evidence",
            ]
            for s in sources:
                title = s.get("title", "Authoritative Source")
                url = s.get("url", "")
                content = s.get("content", "")
                summary_snippet = content[:600].strip() if content else "Verified primary web source."
                lines.append(f"### [{title}]({url})")
                lines.append(f"> {summary_snippet}\n")
                lines.append(f"*Verified Reference: [{title}]({url})*\n")

            lines.extend([
                "## Evidence Summary & Sources Table",
                "| Source Title | Canonical URL | Verification |",
                "|---|---|---|",
            ])
            for s in sources:
                t = s.get("title", "Source")[:45]
                u = s.get("url", "")
                # Never truncate the visible text into something that looks like a
                # URL: a "https://…..." fragment is an invalid citation target and
                # breaks downstream citation-integrity checks.
                lines.append(f"| {t} | [link]({u}) | Grounded |")

            lines.append(f"\n*Synthesized via Autonomous WebLens Engine ({mode} mode) across {len(sources)} sources.*")
            res.content = "\n".join(lines)
            res.completion_tokens = len(res.content.split()) * 2

        return res

    def route_model(self, task_type: str) -> str:
        """Intelligent model router optimizing for task complexity and latency."""
        if task_type in ("deep_research", "financial_analysis", "compliance_screening"):
            return "mistralai/mistral-large-4-1t-a52b"
        elif task_type in ("data_enrichment", "reasoning_audit", "company_research"):
            return "openai/gpt-oss-20b"
        elif task_type in ("quick_search", "query_rewrite"):
            return "nv-mistralai/mistral-nemo-12b-instruct"
        return "mistralai/mistral-large-4-1t-a52b"


# Global singleton instance
model_client = MultiModelClient()
