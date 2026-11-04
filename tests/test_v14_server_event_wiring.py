from __future__ import annotations

from types import SimpleNamespace

import pytest

import server
from security import SecurityValidationError


@pytest.mark.asyncio
async def test_root_tool_wrapper_records_attempt_and_success(monkeypatch):
    events = []

    class FakeStore:
        async def record_event(self, event):
            events.append(event)

    monkeypatch.setattr(server, "event_store", FakeStore())
    result = await server._recorded_operation(
        "search", "web_search", lambda: _result(), provider="test_provider"
    )
    assert result.status == "ok"
    assert [event.status for event in events] == ["attempted", "success"]
    assert all(event.capability == "search" for event in events)
    assert events[-1].provider == "test_provider"


@pytest.mark.asyncio
async def test_root_tool_wrapper_records_failure_and_reraises(monkeypatch):
    events = []

    class FakeStore:
        async def record_event(self, event):
            events.append(event)

    async def fail():
        raise ValueError("controlled failure")

    monkeypatch.setattr(server, "event_store", FakeStore())
    with pytest.raises(ValueError, match="controlled failure"):
        await server._recorded_operation("extract", "extract_url", fail)
    assert [event.status for event in events] == ["attempted", "failed"]
    assert events[-1].details["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_root_tool_wrapper_records_blocked_security_failure(monkeypatch):
    events = []

    class FakeStore:
        async def record_event(self, event):
            events.append(event)

    async def blocked():
        raise SecurityValidationError("private destination")

    monkeypatch.setattr(server, "event_store", FakeStore())
    with pytest.raises(SecurityValidationError, match="private destination"):
        await server._recorded_operation("browser", "browser_navigate", blocked)
    assert [event.status for event in events] == ["attempted", "blocked"]
    assert events[-1].details["error_type"] == "SecurityValidationError"


async def _result():
    return SimpleNamespace(status="ok")
