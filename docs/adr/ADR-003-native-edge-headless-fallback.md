# ADR-003: On-Demand Native Microsoft Edge Headless Execution

## Status
Accepted

## Context
A significant proportion of modern technical documentation (e.g., sites built with Docusaurus, Next.js, VitePress, or React SPAs) renders content dynamically via JavaScript. Pure HTTP GET requests retrieve an empty `<div id="root"></div>` shell.
However, running persistent browser daemons (via Playwright MCP or Puppeteer) consumes 500 MB to 1.5 GB of RAM constantly and adds 3–5 seconds of startup latency, creating severe resource contention on a 16 GB developer workstation running IDEs and local LLMs (Ollama / LM Studio).

## Decision
1. Default to in-process HTTP extraction via `httpx` and Trafilatura (15ms, 0 RAM).
2. Inspect the extracted text: if the extracted content contains fewer than 200 characters and the raw HTML contains SPA markers (`id="root"`, `id="app"`, `<noscript>`), trigger an on-demand fallback.
3. The fallback invokes the native Windows 11 Microsoft Edge binary (`msedge.exe`) with `--headless --dump-dom` via an asynchronous subprocess with an 8.0-second watchdog.
4. Immediately terminate the subprocess once the DOM string is captured and parse it using Trafilatura.

## Consequences
- **Positive**: 0 MB idle RAM footprint; no Docker or Node.js dependencies; 100% SPA extraction coverage on Windows 11 workstations.
- **Negative**: Edge fallback requests take ~2.5s–3.5s due to browser process spawning and JS execution (only incurred on dynamic SPAs).
