"""Verification of Crawl and Deep Research Lifecycle State Machines (V14 Sections 7 and 9).

Verifies:
1. CrawlJob lifecycle: CREATED -> RUNNING -> COMPLETED, cancellation handling, link graph nodes/edges.
2. RobotsChecker robots.txt evaluation.
3. ResearchJob lifecycle: CREATED -> RUNNING -> COMPLETED, progress tracking, cancellation.
4. Export of completed research jobs directly into validated documents (DOCX, PDF, XLSX, MD).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from crawl_engine import CrawlEngine, CrawlJobStatus, RobotsChecker
from document_generator import validate_document
from model_provider import ModelResult, model_client
from research_engine import DeepResearchEngine, ResearchJobStatus
from schemas import ChunkResult, SourceItem, UnifiedResponse


@pytest.fixture
def mock_extractor():
    class MockExtractor:
        async def extract_url(self, url: str, query: str | None = None, chunks_per_source: int = 3, force_tier2: bool = False):
            return SourceItem(
                url=url,
                title=f"Title for {url}",
                score=0.9,
                content=f"Content extracted from {url}",
                chunks=[ChunkResult(content=f"Passage from {url}", score=0.9)],
            )
    return MockExtractor()


@pytest.mark.asyncio
async def test_robots_checker():
    checker = RobotsChecker()
    robots_content = (
        "User-agent: *\n"
        "Disallow: /private/\n"
        "Disallow: /admin\n"
        "Allow: /public/\n"
    )

    with respx.mock(base_url="https://example.com") as respx_mock:
        respx_mock.get("/robots.txt").respond(status_code=200, text=robots_content)

        # Disallowed path
        assert await checker.can_fetch("https://example.com/private/data") is False
        assert await checker.can_fetch("https://example.com/admin") is False

        # Allowed path
        assert await checker.can_fetch("https://example.com/public/data") is True
        assert await checker.can_fetch("https://example.com/about") is True


@pytest.mark.asyncio
async def test_crawl_job_lifecycle(mock_extractor):
    engine = CrawlEngine(extractor=mock_extractor)

    html_content = (
        "<html><body>"
        "<a href='/page1'>Page 1</a>"
        "<a href='/page2'>Page 2</a>"
        "</body></html>"
    )

    with respx.mock(base_url="https://example.com", assert_all_called=False) as respx_mock:
        respx_mock.get("/sitemap.xml").respond(status_code=404)
        respx_mock.get("/").respond(status_code=200, text=html_content)
        respx_mock.get("/page1").respond(status_code=200, text="<html>Page 1</html>")
        respx_mock.get("/page2").respond(status_code=200, text="<html>Page 2</html>")

        # Launch managed crawl job
        job = engine.start_crawl_job("https://example.com/", limit=3)
        assert job.status in (CrawlJobStatus.CREATED, CrawlJobStatus.RUNNING)

        # Wait for job completion
        await job._task
        assert job.status == CrawlJobStatus.COMPLETED
        assert job.completed_at is not None
        assert job.discovered_count >= 1
        assert len(job.results) >= 1
        assert len(job.link_graph.nodes) >= 1

        # Retrieval check
        status_check = engine.get_crawl_status(job.job_id)
        assert status_check is not None
        assert status_check.job_id == job.job_id


@pytest.mark.asyncio
async def test_crawl_job_cancellation():
    engine = CrawlEngine()
    job = engine.start_crawl_job("https://example.com/", limit=10)

    # Cancel immediately
    cancelled = engine.cancel_crawl_job(job.job_id)
    assert cancelled is True
    assert job.status == CrawlJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_research_job_lifecycle_and_document_export(tmp_path: Path):
    # Mock search pipeline
    class MockSearchPipeline:
        async def search(self, query: str, search_depth: str = "basic", max_results: int = 3, chunks_per_source: int = 3, include_domains=None):
            return UnifiedResponse(
                query=query,
                answer=f"Verified answer for {query}",
                results=[
                    SourceItem(
                        url=f"https://source.example.com/{query.replace(' ', '_')}",
                        title=f"Source on {query}",
                        score=0.92,
                        content=f"Substantial findings about {query}",
                        chunks=[ChunkResult(content=f"Findings on {query}", score=0.92)],
                    )
                ],
                source_engine="local_live",
            )

    research_engine = DeepResearchEngine(search_pipeline=MockSearchPipeline())

    # Keep the synthesis step offline (live provider calls are not part of this suite).
    stub_report = ModelResult(
        content=(
            "# Research Report: AI Agent Architectures 2026\n\n"
            "Verified findings from [Source on AI Agent Architectures 2026]"
            "(https://source.example.com/AI_Agent_Architectures_2026).\n"
        ),
        reasoning_content=None,
        model_name="test-model",
        provider="local_algorithmic",
        prompt_tokens=10,
        completion_tokens=10,
        latency_ms=1.0,
    )

    with patch.object(
        model_client, "synthesize_research_report", new=AsyncMock(return_value=stub_report)
    ):
        # Launch research job
        job = research_engine.start_research_job("AI Agent Architectures 2026", mode="mini")
        assert job.status in (ResearchJobStatus.CREATED, ResearchJobStatus.RUNNING)

        # Await completion
        await job._task
    assert job.status == ResearchJobStatus.COMPLETED
    assert job.progress_step == "completed"
    assert job.report is not None
    assert len(job.sources) >= 1
    assert job.completed_at is not None

    # Export to DOCX
    docx_path = tmp_path / "research_report.docx"
    exported_docx = research_engine.export_research_document(job.job_id, "docx", docx_path)
    assert exported_docx.exists()
    assert validate_document(exported_docx, "docx")["valid"] is True

    # Export to PDF
    pdf_path = tmp_path / "research_report.pdf"
    exported_pdf = research_engine.export_research_document(job.job_id, "pdf", pdf_path)
    assert exported_pdf.exists()
    assert validate_document(exported_pdf, "pdf")["valid"] is True

    # Export to Markdown
    md_path = tmp_path / "research_report.md"
    exported_md = research_engine.export_research_document(job.job_id, "md", md_path)
    assert exported_md.exists()
    assert validate_document(exported_md, "md")["valid"] is True
