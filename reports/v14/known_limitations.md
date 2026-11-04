# V14 Known Limitations

- Multiple overlapping server implementations remain.
- Geographic mapping is absent.
- Controlled browser sessions and interaction permissions are absent.
- Crawl and research jobs are not a demonstrated persistent state machine.
- Dashboard frontend and canonical tool-to-event wiring are not established;
  `event_store.py` exists but is currently a separately tested component.
- Separate REST API is absent.
- Document generation is absent.
- Gemini comparison is blocked by missing environment key.
- Playwright is installed as a Python package, but browser binary availability
  and end-to-end browser gates are not established by this audit.
- Global Python does not have all project test dependencies; use `.venv`.
- Current worktree is dirty and contains concurrent changes.
- Live-provider quality scores vary with provider availability, cache state,
  and web content; no single run proves production accuracy.
