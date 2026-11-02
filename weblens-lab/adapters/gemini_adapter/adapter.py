"""Google Gemini Provider Adapter for Four-System Evaluation Lab.

Supports:
- Mode G1: Native Gemini (using gemini-2.5-flash / gemini-2.0-flash with Google Search Grounding)
- Mode G2: Gemini + WebLens MCP composition
- Mode G3: Gemini + Tavily composition
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..common_interface.base import (
    AnswerResponse,
    ExtractItem,
    ExtractResponse,
    ProviderUsage,
    ResearchProvider,
    ResearchResponse,
    SearchItem,
    SearchResponse,
)


class GeminiAdapter(ResearchProvider):
    """Adapter for Google Gemini API and Search Grounding."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")

        if not self._api_key:
            # Check project .env
            for cand in [Path(".env"), Path("../.env"), Path("../../.env")]:
                if cand.exists():
                    for line in cand.read_text(encoding="utf-8").splitlines():
                        if line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_API_KEY="):
                            self._api_key = line.split("=", 1)[1].strip()
                            break
                    if self._api_key:
                        break

        self._usage = ProviderUsage()
        self._client: Any = None

        if self._api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except Exception:
                self._client = None

    @property
    def name(self) -> str:
        return "gemini_native"

    @property
    def is_independent(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        return bool(self._client and self._api_key)

    async def search(self, query: str, *, max_results: int = 5, **options: Any) -> SearchResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        if not self.is_available:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return SearchResponse(
                provider=self.name,
                query=query,
                results=[],
                status="error",
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error="BLOCKED: GEMINI_API_KEY is missing or invalid in .env",
            )

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            )

            prompt = f"Perform a web search and report authoritative sources for: {query}"
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.total_latency_ms += elapsed_ms

            # Extract search grounding chunks
            items: list[SearchItem] = []
            candidates = getattr(response, "candidates", []) or []
            toks = getattr(response, "usage_metadata", None)
            total_tokens = getattr(toks, "total_token_count", 0) if toks else 0

            for cand in candidates:
                grounding = getattr(cand, "grounding_metadata", None)
                if grounding:
                    chunks = getattr(grounding, "grounding_chunks", []) or []
                    for c in chunks:
                        web = getattr(c, "web", None)
                        if web:
                            items.append(
                                SearchItem(
                                    url=getattr(web, "uri", ""),
                                    title=getattr(web, "title", ""),
                                    content=getattr(response, "text", "")[:300],
                                    published_date=None,
                                )
                            )

            # Fallback if text returned but no explicit chunks
            if not items and getattr(response, "text", ""):
                items.append(
                    SearchItem(
                        url="https://google.com/search",
                        title="Google Grounded Search Summary",
                        content=response.text[:300],
                    )
                )

            self._usage.successful_requests += 1
            self._usage.output_tokens += total_tokens

            return SearchResponse(
                provider=self.name,
                query=query,
                results=items[:max_results],
                status="ok" if items else "no_reliable_result",
                latency_ms=elapsed_ms,
                tokens_returned=total_tokens,
                credits_used=0.0,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return SearchResponse(
                provider=self.name,
                query=query,
                results=[],
                status="error",
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error=str(e),
            )

    async def extract(self, urls: list[str], **options: Any) -> ExtractResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        if not self.is_available:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return ExtractResponse(
                provider=self.name,
                results=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error="BLOCKED: GEMINI_API_KEY is missing",
            )

        items: list[ExtractItem] = []
        total_tokens = 0

        try:
            for u in urls[:3]:
                prompt = f"Extract and summarize the factual content from this URL: {u}"
                res = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                )
                text = getattr(res, "text", "") or ""
                toks = getattr(res, "usage_metadata", None)
                count = getattr(toks, "total_token_count", 0) if toks else 0
                total_tokens += count
                items.append(
                    ExtractItem(
                        url=u,
                        raw_content=text,
                        markdown=text,
                        status="ok" if text else "failed",
                    )
                )

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.successful_requests += 1
            self._usage.output_tokens += total_tokens

            return ExtractResponse(
                provider=self.name,
                results=items,
                latency_ms=elapsed_ms,
                tokens_returned=total_tokens,
                credits_used=0.0,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ExtractResponse(
                provider=self.name,
                results=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                error=str(e),
            )

    async def crawl(self, url: str, *, max_pages: int = 10, **options: Any) -> ExtractResponse:
        # Gemini does not natively perform recursive website crawling
        t0 = time.perf_counter()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return ExtractResponse(
            provider=self.name,
            results=[],
            latency_ms=elapsed_ms,
            tokens_returned=0,
            credits_used=0.0,
            error="UNSUPPORTED: Native Gemini API does not provide recursive site crawling",
        )

    async def answer(self, query: str, **options: Any) -> AnswerResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        if not self.is_available:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return AnswerResponse(
                provider=self.name,
                query=query,
                answer="",
                citations=[],
                confidence=0.0,
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                status="error",
                error="BLOCKED: GEMINI_API_KEY is missing",
            )

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            )

            prompt = f"Answer the following question with verified factual claims and cite your sources: {query}"
            res = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            text = getattr(res, "text", "") or ""
            toks = getattr(res, "usage_metadata", None)
            total_tokens = getattr(toks, "total_token_count", 0) if toks else 0

            citations = []
            candidates = getattr(res, "candidates", []) or []
            for cand in candidates:
                grounding = getattr(cand, "grounding_metadata", None)
                if grounding:
                    chunks = getattr(grounding, "grounding_chunks", []) or []
                    for c in chunks:
                        web = getattr(c, "web", None)
                        if web:
                            citations.append({
                                "url": getattr(web, "uri", ""),
                                "title": getattr(web, "title", ""),
                            })

            self._usage.successful_requests += 1
            self._usage.output_tokens += total_tokens

            return AnswerResponse(
                provider=self.name,
                query=query,
                answer=text,
                citations=citations,
                confidence=0.9 if citations else 0.5,
                latency_ms=elapsed_ms,
                tokens_returned=total_tokens,
                credits_used=0.0,
                status="ok" if text else "uncertain",
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return AnswerResponse(
                provider=self.name,
                query=query,
                answer="",
                citations=[],
                confidence=0.0,
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                status="error",
                error=str(e),
            )

    async def research(self, query: str, **options: Any) -> ResearchResponse:
        t0 = time.perf_counter()
        self._usage.requests += 1

        if not self.is_available:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown="",
                subqueries=[],
                sources=[],
                contradictions=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                status="error",
                error="BLOCKED: GEMINI_API_KEY is missing",
            )

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
            )

            prompt = (
                f"You are an expert research analyst. Conduct a thorough investigation on: {query}\n"
                "Provide an Executive Summary, Key Findings, Contradictory Evidence, and full source citations."
            )

            res = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            text = getattr(res, "text", "") or ""
            toks = getattr(res, "usage_metadata", None)
            total_tokens = getattr(toks, "total_token_count", 0) if toks else 0

            sources = []
            candidates = getattr(res, "candidates", []) or []
            for cand in candidates:
                grounding = getattr(cand, "grounding_metadata", None)
                if grounding:
                    chunks = getattr(grounding, "grounding_chunks", []) or []
                    for c in chunks:
                        web = getattr(c, "web", None)
                        if web:
                            sources.append({
                                "url": getattr(web, "uri", ""),
                                "title": getattr(web, "title", ""),
                            })

            self._usage.successful_requests += 1
            self._usage.output_tokens += total_tokens

            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown=text,
                subqueries=[query],
                sources=sources,
                contradictions=[],
                latency_ms=elapsed_ms,
                tokens_returned=total_tokens,
                credits_used=0.0,
                status="ok" if text else "partial",
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._usage.failed_requests += 1
            return ResearchResponse(
                provider=self.name,
                query=query,
                report_markdown="",
                subqueries=[],
                sources=[],
                contradictions=[],
                latency_ms=elapsed_ms,
                tokens_returned=0,
                credits_used=0.0,
                status="error",
                error=str(e),
            )

    def get_usage(self) -> ProviderUsage:
        return self._usage

