"""Exercise every full-profile MCP tool closure with local fakes.

The core MCP surface is covered elsewhere; this file reaches the research and
stateful tool bodies that are only registered for the ``full`` profile.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from weblens import mcp_server


class FakeSettings:
    log_level = "INFO"
    mcp_profile = "full"
    cache_dir = None


class FakeService:
    def __init__(self, cache_dir):
        self.s = FakeSettings()
        self.s.cache_dir = cache_dir
        self.calls: list[tuple[str, dict]] = []

    async def search(self, query, **kwargs):
        self.calls.append(("search", {"query": query, **kwargs}))
        return {"status": "ok", "res": [{"t": "T", "u": "https://e.com", "s": "S"}]}

    async def extract(self, url, **kwargs):
        return {"status": "ok", "u": url}

    async def crawl_site(self, url, **kwargs):
        return {"status": "ok", "u": url}

    async def deep_research(self, query, **kwargs):
        return {"status": "ok", "q": query}

    async def synthesize(self, query, **kwargs):
        return {"status": "ok", "q": query}


async def test_full_profile_tool_closures_forward_to_apps(tmp_path, monkeypatch):
    from weblens.apps import company, crawl2rag, market, meeting, research_chat, sheets, tutorial_101

    class Company:
        def __init__(self, service):
            self.service = service

        async def research_company(self, name):
            return {"status": "ok", "company": name}

    class Market:
        def __init__(self, service):
            self.service = service

        async def analyze_asset(self, asset, question=None):
            return {"status": "ok", "asset": asset, "question": question}

        async def analyze_portfolio(self, assets):
            return {"status": "ok", "assets": assets}

    class Meeting:
        def __init__(self, service):
            self.service = service

        async def prepare_brief(self, title, attendees, company_or_org=None):
            return {"status": "ok", "title": title, "company": company_or_org}

    class Sheets:
        def __init__(self, service):
            self.service = service

        async def enrich_records(self, rows, prompts):
            return {"status": "ok", "rows": rows, "prompts": prompts}

    class Rag:
        def __init__(self, service, db_path=None):
            self.db_path = db_path

        async def ingest(self, url, max_pages=5):
            return {"status": "ok", "url": url, "max_pages": max_pages}

        async def query(self, question, top_k=5):
            return {"status": "ok", "q": question, "top_k": top_k}

    class Chat:
        def __init__(self, service, db_path=None, session_id=None):
            self.session_id = session_id or "generated"

        async def send_query(self, message):
            return SimpleNamespace(
                id="m1",
                role="assistant",
                content=message,
                citations=[],
                tokens_used=1,
            )

    async def fake_tutorial(service, step="all"):
        return {"status": "ok", "step": step}

    monkeypatch.setattr(company, "CompanyResearcher", Company)
    monkeypatch.setattr(market, "MarketResearcher", Market)
    monkeypatch.setattr(crawl2rag, "Crawl2RAG", Rag)
    monkeypatch.setattr(meeting, "MeetingPrepAgent", Meeting)
    monkeypatch.setattr(research_chat, "PersistentResearchChat", Chat)
    monkeypatch.setattr(sheets, "SheetsEnricher", Sheets)
    monkeypatch.setattr(tutorial_101, "run_tutorial", fake_tutorial)

    service = FakeService(tmp_path)
    server = mcp_server.build_server(service, profile="full")

    cases = [
        ("company_research", {"company": "Acme"}),
        ("market_research", {"asset": "ACME", "question": "revenue"}),
        ("market_portfolio", {"assets": ["A", "B"]}),
        ("meeting_prep", {"meeting_title": "Sync", "attendees": ["Ada"], "company_or_org": "Acme"}),
        ("sheets_enrich", {"rows": [{"company": "Acme"}], "column_prompts": {"revenue": "revenue"}}),
        ("crawl2rag_index", {"url": "https://e.com", "max_pages": 2}),
        ("crawl2rag_query", {"question": "what", "top_k": 2}),
        ("research_chat", {"message": "hello", "session_id": "s1"}),
        ("research_chat", {"message": "again"}),
        ("tutorial_101", {"step": "search"}),
    ]
    # Each stub echoes the arguments it received, so the assertion below proves the
    # closure actually forwarded them. Previously this only checked
    # `is_error is False`, which an app that ignored every argument still passed.
    expectations = {
        "company_research": ("company", "Acme"),
        "market_research": ("asset", "ACME"),
        "market_portfolio": ("assets", ["A", "B"]),
        "meeting_prep": ("title", "Sync"),
        "sheets_enrich": ("prompts", {"revenue": "revenue"}),
        "crawl2rag_index": ("url", "https://e.com"),
        "crawl2rag_query": ("q", "what"),
        "research_chat": ("content", "hello"),
        "tutorial_101": ("step", "search"),
    }
    for name, args in cases:
        result = await server.call_tool(name, args)
        assert result.is_error is False, name

        # Flatten the MCP content payload to text/JSON for inspection.
        payload = result.content[0].text if result.content else ""
        assert payload, f"{name}: empty payload"

        key, expected = expectations[name]
        if name == "research_chat":
            expected = args["message"]  # the chat stub echoes the user message
        assert key in payload, f"{name}: forwarded argument {key!r} missing from result"

        # Compare structurally rather than by substring: the closure serialises the
        # result to JSON, and separators/ordering need not match repr() or
        # json.dumps defaults. A no-forwarding stub would omit the value entirely.
        def _norm(text: str) -> str:
            return text.replace(" ", "").replace("'", '"')

        needles = [_norm(json.dumps(expected)), _norm(str(expected))]
        assert any(n in _norm(payload) for n in needles), (
            f"{name}: the closure did not forward {key}={expected!r}; got {payload[:200]}"
        )
