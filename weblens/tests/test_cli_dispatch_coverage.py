"""Coverage for cli.py app dispatch, schema report and payload helpers.

Everything here runs in-process: app classes are monkeypatched so no network,
browser or LLM call happens, and `_emit` / `_schema_report` / `_serve_http`
are invoked directly with their I/O boundary stubbed.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pytest

from weblens import cli
from weblens.config import Settings


def _settings() -> Settings:
    return Settings(cache_dir=Path(tempfile.mkdtemp()), cache_enabled=False)


class FakeService:
    """Minimal WebLens stand-in: real Settings, close() recorded."""

    def __init__(self, settings=None, *a, **kw):
        self.s = settings or _settings()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _ns(**kw) -> argparse.Namespace:
    base = dict(
        app_name="company",
        company="Acme",
        asset="ACME",
        question=None,
        portfolio=None,
        message="hi",
        session_id=None,
        title="Sync",
        attendee=["Ada"],
        company_or_org=None,
        input_csv="in.csv",
        output_csv="out.csv",
        col=[],
        step="all",
        target="https://example.com",
        max_pages=2,
        top_k=3,
        action="stats",
        pretty=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture(autouse=True)
def _patch_service(monkeypatch):
    monkeypatch.setattr(cli, "WebLens", FakeService)


@pytest.mark.asyncio
async def test_run_app_company(monkeypatch):
    from weblens.apps import company

    async def fake_research(self, name):
        return {"status": "ok", "company": name}

    monkeypatch.setattr(company.CompanyResearcher, "research_company", fake_research)
    assert await cli._run_app(_ns(app_name="company")) == 0


@pytest.mark.asyncio
async def test_run_app_market_asset_and_portfolio(monkeypatch):
    from weblens.apps import market

    async def fake_asset(self, asset, question=None):
        return {"status": "ok", "asset": asset}

    async def fake_portfolio(self, assets):
        return {"status": "ok", "portfolio_size": len(assets)}

    monkeypatch.setattr(market.MarketResearcher, "analyze_asset", fake_asset)
    monkeypatch.setattr(market.MarketResearcher, "analyze_portfolio", fake_portfolio)

    assert await cli._run_app(_ns(app_name="market")) == 0
    assert await cli._run_app(_ns(app_name="market", portfolio=["AAPL", "MSFT"])) == 0


@pytest.mark.asyncio
async def test_run_app_chat_and_meeting(monkeypatch):
    from weblens.apps import chat, meeting

    async def fake_send_message(self, message):
        return {"status": "ok", "content": "reply"}

    async def fake_brief(self, title, attendees, company_or_org=None):
        return {"status": "ok", "title": title}

    monkeypatch.setattr(chat.ResearchChatSession, "send_message", fake_send_message)
    monkeypatch.setattr(meeting.MeetingPrepAgent, "prepare_brief", fake_brief)

    assert await cli._run_app(_ns(app_name="chat")) == 0
    assert await cli._run_app(_ns(app_name="meeting")) == 0


@pytest.mark.asyncio
async def test_run_app_research_chat_and_tutorial(monkeypatch):
    from weblens.apps import research_chat, tutorial_101

    class Msg:
        role = "assistant"
        content = "reply"
        citations = ["https://example.com"]
        tokens_used = 3

    async def fake_send_query(self, message):
        return Msg()

    async def fake_tutorial(service, step="all"):
        return {"status": "ok", "step": step}

    monkeypatch.setattr(research_chat.PersistentResearchChat, "send_query", fake_send_query)
    monkeypatch.setattr(tutorial_101, "run_tutorial", fake_tutorial)

    assert await cli._run_app(_ns(app_name="research-chat")) == 0
    assert await cli._run_app(_ns(app_name="tutorial", step="search")) == 0


@pytest.mark.asyncio
async def test_run_app_sheets_parses_column_specs(monkeypatch):
    from weblens.apps import sheets

    captured = {}

    async def fake_csv(self, in_path, out_path, cols):
        captured["cols"] = cols
        return {"status": "ok", "processed_rows": 0}

    monkeypatch.setattr(sheets.SheetsEnricher, "process_csv", fake_csv)

    code = await cli._run_app(_ns(app_name="sheets", col=["a=1", "b", " c = 2 "]))

    assert code == 0
    assert captured["cols"] == {"a": "1", "c": "2"}


@pytest.mark.asyncio
async def test_run_app_crawl2rag_actions(monkeypatch):
    from weblens.apps import crawl2rag

    async def fake_ingest(self, url, max_pages=5):
        return {"status": "ok", "pages_indexed": 1}

    async def fake_query(self, question, top_k=5):
        return {"status": "ok", "n": top_k}

    def fake_stats(self):
        return {"status": "ok", "passages": 0}

    monkeypatch.setattr(crawl2rag.Crawl2RAG, "ingest", fake_ingest)
    monkeypatch.setattr(crawl2rag.Crawl2RAG, "query", fake_query)
    monkeypatch.setattr(crawl2rag.Crawl2RAG, "stats", fake_stats)

    assert await cli._run_app(_ns(app_name="crawl2rag", action="ingest")) == 0
    assert await cli._run_app(_ns(app_name="crawl2rag", action="query")) == 0
    assert await cli._run_app(_ns(app_name="crawl2rag", action="stats")) == 0


@pytest.mark.asyncio
async def test_run_app_unknown_app_returns_error_exit():
    assert await cli._run_app(_ns(app_name="nope")) == 1


def test_emit_compact_and_pretty(capsys):
    cli._emit({"status": "ok", "n": 1}, False)
    assert json.loads(capsys.readouterr().out.strip())["n"] == 1

    cli._emit({"status": "ok", "n": 2}, True)
    pretty = capsys.readouterr().out
    assert json.loads(pretty)["n"] == 2
    assert "\n" in pretty.strip()


def test_configure_stdout_is_safe():
    cli._configure_stdout()  # must not raise on any platform


def test_build_parser_accepts_every_subcommand():
    parser = cli._build_parser()
    for argv in (
        ["serve", "--profile", "full"],
        ["search", "python asyncio"],
        ["extract", "https://example.com"],
        ["crawl", "https://example.com", "--mode", "map"],
        ["research", "quantum"],
        ["synthesize", "claim"],
        ["doctor"],
        ["cache", "purge"],
        ["tokens", "--pretty"],
        ["app", "company", "Anthropic"],
        ["app", "market", "AAPL", "--portfolio", "MSFT"],
        ["app", "tutorial", "--step", "all"],
    ):
        assert parser.parse_args(argv).command == argv[0]


@pytest.mark.asyncio
async def test_schema_report_measures_profiles(monkeypatch):
    from weblens import mcp_server

    class FakeTool:
        name = "web_search"

        def model_dump(self, by_alias=True, exclude_none=True):
            return {"name": "web_search", "description": "d", "inputSchema": {}}

    class FakeServer:
        async def list_tools(self):
            return [FakeTool(), FakeTool()]

    monkeypatch.setattr(mcp_server, "build_server", lambda svc, profile=None: FakeServer())

    report = await cli._schema_report()

    assert report["status"] == "ok"
    assert set(report["profiles"]) == {"core", "research", "full"}
    assert report["profiles"]["core"]["tool_count"] == 2
    assert report["profiles"]["core"]["total_tokens"] > 0


def test_transport_security_defaults_are_protective():
    ts = cli._transport_security_settings(Settings())
    assert ts.enable_dns_rebinding_protection is True
    assert "localhost" in ts.allowed_hosts
    assert "*" not in ts.allowed_hosts


def test_transport_security_wildcard_is_explicit_opt_out():
    ts = cli._transport_security_settings(Settings(allowed_hosts="*", allowed_origins="*"))
    assert ts.enable_dns_rebinding_protection is False


def test_serve_http_refuses_non_loopback_without_token(monkeypatch, capsys):
    args = cli._build_parser().parse_args(["serve", "--http", "--host", "0.0.0.0", "--port", "1"])
    monkeypatch.delenv("WEBLENS_HTTP_TOKEN", raising=False)
    monkeypatch.delenv("WEBLENS_API_KEYS", raising=False)

    code = cli._serve_http(args)

    assert code == 2
    assert "refusing" in capsys.readouterr().err.lower()


def test_serve_http_wires_app_and_runs(monkeypatch):
    """Exercise the serve wiring with uvicorn stubbed out."""
    import uvicorn

    called: dict = {}

    class FakeServer:
        def __init__(self, config):
            called["config"] = config

        async def serve(self):
            called["served"] = True

    monkeypatch.setattr(uvicorn, "Server", FakeServer)

    args = cli._build_parser().parse_args(
        ["serve", "--http", "--host", "127.0.0.1", "--port", "8799", "--profile", "core"]
    )
    code = cli._serve_http(args)

    assert code == 0
    assert called.get("served") is True
    assert called["config"].host == "127.0.0.1"
