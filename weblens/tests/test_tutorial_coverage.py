"""Coverage tests for the WebLens 101 tutorial.

Each test stubs the underlying services so the tutorial steps run offline and
assert the reported status/messages.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import weblens.apps.tutorial_101 as tut
from weblens.apps.tutorial_101 import run_tutorial


class FakeService:
    def __init__(self):
        self.doctor = AsyncMock(return_value={"status": "ok", "version": "0.1", "providers": ["ddg", "wikipedia"]})
        self.search = AsyncMock(
            return_value={
                "status": "ok",
                "res": [{"t": "Python asyncio", "u": "https://docs.python.org/3/library/asyncio.html"}],
            }
        )
        self.close = AsyncMock()


class FakeChat:
    def __init__(self, service):
        self.service = service

    async def send_message(self, message):
        return {"answer": "Asyncio is great.", "citations": [{"u": "https://docs.python.org/3/library/asyncio.html"}]}


class FakeCompany:
    def __init__(self, service):
        self.service = service

    async def research_company(self, company):
        return {"status": "found", "detected_domain": "python.org"}


class FakeMarket:
    def __init__(self, service):
        self.service = service

    async def analyze_asset(self, asset, question=None):
        return {"disclosures_found": 1, "verified_metrics": [{"metric": "PE"}]}

    async def analyze_portfolio(self, portfolio):
        return {"assets": []}


class FakeSheets:
    def __init__(self, service):
        self.service = service

    async def enrich_records(self, records, prompts):
        return {
            "total_rows": 2,
            "records": [
                {"CEO": "Tim Cook", "CEO_status": "verified"},
                {"CEO": "Satya Nadella", "CEO_status": "verified"},
            ],
        }


class FakeMeeting:
    def __init__(self, service):
        self.service = service

    async def prepare_brief(self, title, attendees, company_or_org=None):
        return {
            "attendees_researched": 1,
            "attendee_profiles": [{"name": "Guido", "sources": ["https://python.org"]}],
            "privacy_notice": "Public sources only.",
        }


class FakeCrawl2RAG:
    def __init__(self, service, db_path=None):
        self.service = service
        self._db = db_path

    async def ingest(self, url, max_pages=1, max_depth=0):
        return {"pages_crawled": 1}

    def stats(self):
        return {"documents": 1, "passages": 1}

    async def query(self, question, top_k=3):
        return {"n": 1, "passages": [{"text": "asyncio"}]}


class FakeDeepResearch:
    def __init__(self, service):
        self.service = service

    async def execute_research(self, query, max_tokens=1200):
        return {
            "key_findings": [{"claim": "Tasks are different."}],
            "methodology": {"subqueries_searched": ["q1", "q2"]},
        }


@pytest.fixture
def fake_service(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(tut, "ResearchChatSession", FakeChat)
    monkeypatch.setattr(tut, "CompanyResearcher", FakeCompany)
    monkeypatch.setattr(tut, "MarketResearcher", FakeMarket)
    monkeypatch.setattr(tut, "SheetsEnricher", FakeSheets)
    monkeypatch.setattr(tut, "MeetingPrepAgent", FakeMeeting)
    monkeypatch.setattr(tut, "Crawl2RAG", FakeCrawl2RAG)
    monkeypatch.setattr(tut, "DeepResearchAgent", FakeDeepResearch)
    return service


@pytest.mark.parametrize(
    "step", ["doctor", "search", "chat", "company", "market", "sheets", "meeting", "rag", "deep_research", "all"]
)
async def test_tutorial_step(fake_service, step):
    result = await run_tutorial(fake_service, step=step)
    assert result["status"] == "ok"
    assert result["passed_steps"] == result["total_steps"]
    for key, data in result["steps"].items():
        assert data["status"] == "passed", f"step {key} failed"


async def test_tutorial_creates_own_service(monkeypatch, tmp_path):
    service = FakeService()
    service.doctor.return_value = {"status": "ok", "version": "0.1", "providers": []}
    monkeypatch.setattr(tut, "WebLens", lambda: service)
    monkeypatch.setattr(tut, "ResearchChatSession", FakeChat)
    monkeypatch.setattr(tut, "CompanyResearcher", FakeCompany)
    monkeypatch.setattr(tut, "MarketResearcher", FakeMarket)
    monkeypatch.setattr(tut, "SheetsEnricher", FakeSheets)
    monkeypatch.setattr(tut, "MeetingPrepAgent", FakeMeeting)
    monkeypatch.setattr(tut, "Crawl2RAG", FakeCrawl2RAG)
    monkeypatch.setattr(tut, "DeepResearchAgent", FakeDeepResearch)
    result = await run_tutorial(None, step="doctor")
    assert result["status"] == "partial"
    assert result["steps"]["1_diagnostics"]["status"] == "failed"
    service.close.assert_awaited_once()


async def test_search_retry_when_empty(fake_service):
    fake_service.search.return_value = {"status": "ok", "res": []}
    result = await run_tutorial(fake_service, step="search")
    assert fake_service.search.call_count == 2
    assert result["steps"]["2_web_search"]["status"] == "failed"


async def test_chat_degraded():
    class EmptyChat:
        def __init__(self, service):
            pass

        async def send_message(self, message):
            return {"answer": "", "citations": []}

    original = tut.ResearchChatSession
    try:
        tut.ResearchChatSession = EmptyChat
        result = await run_tutorial(FakeService(), step="chat")
    finally:
        tut.ResearchChatSession = original
    assert result["steps"]["3_research_chat"]["status"] == "degraded"


async def test_sheets_degraded_with_one_verified():
    class OneVerifiedSheets:
        def __init__(self, service):
            pass

        async def enrich_records(self, records, prompts):
            return {
                "total_rows": 2,
                "records": [{"CEO": "Tim", "CEO_status": "verified"}, {"CEO": "", "CEO_status": "unverified"}],
            }

    original = tut.SheetsEnricher
    try:
        tut.SheetsEnricher = OneVerifiedSheets
        result = await run_tutorial(FakeService(), step="sheets")
    finally:
        tut.SheetsEnricher = original
    assert result["steps"]["6_sheets_enrich"]["status"] == "passed"
