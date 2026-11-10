"""WebLens Interactive Demo UI and Documentation Handler.

Serves an interactive web application on GET / when requested by a browser
(Accept: text/html), providing real-time demonstration of web search, content
extraction, and deep research, along with agent connection instructions for the
Streamable HTTP MCP endpoint at /mcp.
"""

from __future__ import annotations

import html
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse


def _escape(text: Any) -> str:
    return html.escape(str(text or ""))


def _build_html(
    *,
    action: str,
    q: str,
    url: str,
    result: Any,
    error: str | None,
    host: str,
) -> str:
    scheme = "https" if "localhost" not in host and "127.0.0.1" not in host else "http"
    mcp_url = f"{scheme}://{host}/mcp"

    claude_config = json.dumps(
        {
            "mcpServers": {
                "weblens": {
                    "url": mcp_url,
                }
            }
        },
        indent=2,
    )

    result_html = ""
    if error:
        result_html = f'<div class="card error-card"><h3>Error</h3><pre>{_escape(error)}</pre></div>'
    elif result is not None:
        if action == "search":
            items = result.get("results") if isinstance(result, dict) else result
            rendered_items = []
            if isinstance(items, list):
                for item in items:
                    title = _escape(item.get("title", "Untitled"))
                    item_url = _escape(item.get("url", "#"))
                    snippet = _escape(item.get("snippet") or item.get("content") or "")
                    provider = _escape(item.get("provider", "web"))
                    score = item.get("score")
                    score_str = f'<span class="badge">score: {score:.2f}</span>' if score is not None else ""
                    rendered_items.append(
                        f'<div class="result-item">'
                        f'  <div class="result-header">'
                        f'    <a href="{item_url}" target="_blank" rel="noopener">{title}</a>'
                        f'    <span class="badge provider">{provider}</span>{score_str}'
                        f'  </div>'
                        f'  <div class="result-url">{item_url}</div>'
                        f'  <div class="result-snippet">{snippet}</div>'
                        f'</div>'
                    )
            result_html = f'<div class="card results-card"><h3>Search Results ({len(items) if isinstance(items, list) else 0})</h3>{"".join(rendered_items)}</div>'
        elif action == "extract":
            md = result.get("markdown") or result.get("content") if isinstance(result, dict) else str(result)
            title = result.get("title", "Extracted Document") if isinstance(result, dict) else "Extraction"
            result_html = (
                f'<div class="card results-card">'
                f'  <h3>{_escape(title)}</h3>'
                f'  <pre class="code-preview">{_escape(md)}</pre>'
                f'</div>'
            )
        elif action == "research":
            report = result.get("report") if isinstance(result, dict) else str(result)
            sources = result.get("sources", []) if isinstance(result, dict) else []
            source_links = [
                f'<li><a href="{_escape(s)}" target="_blank">{_escape(s)}</a></li>'
                for s in sources
            ]
            result_html = (
                f'<div class="card results-card">'
                f'  <h3>Research Synthesis</h3>'
                f'  <div class="report-content"><pre class="code-preview">{_escape(report)}</pre></div>'
                f'  <h4>Sources Consulted ({len(sources)})</h4>'
                f'  <ul>{"".join(source_links)}</ul>'
                f'</div>'
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>WebLens - Personal Web Intelligence & MCP Server</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0ea5e9;
      --accent: #10b981;
      --danger: #ef4444;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      line-height: 1.6;
      padding: 24px 16px;
    }}
    .container {{
      max-width: 1040px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand h1 {{
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: var(--primary);
    }}
    .badge {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(56, 189, 248, 0.15);
      color: var(--primary);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    .badge.online {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent);
      border-color: rgba(16, 185, 129, 0.3);
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 22px;
      margin-bottom: 24px;
    }}
    .tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
    }}
    .tab-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 15px;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .tab-btn.active, .tab-btn:hover {{
      color: var(--primary);
      background: rgba(56, 189, 248, 0.1);
    }}
    .form-group {{
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .form-input {{
      flex: 1;
      background: #0b1120;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 12px 16px;
      border-radius: 6px;
      font-size: 15px;
    }}
    .form-input:focus {{
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
    }}
    .btn {{
      background: var(--primary);
      color: #0f172a;
      border: none;
      font-weight: 600;
      font-size: 15px;
      padding: 12px 24px;
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.15s;
    }}
    .btn:hover {{ background: var(--primary-hover); }}
    .result-item {{
      padding: 14px 0;
      border-bottom: 1px solid var(--border);
    }}
    .result-item:last-child {{ border-bottom: none; }}
    .result-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 4px;
    }}
    .result-header a {{
      color: var(--primary);
      font-size: 17px;
      font-weight: 600;
      text-decoration: none;
    }}
    .result-header a:hover {{ text-decoration: underline; }}
    .result-url {{
      color: var(--text-muted);
      font-size: 13px;
      margin-bottom: 6px;
      word-break: break-all;
    }}
    .result-snippet {{
      color: #cbd5e1;
      font-size: 14px;
    }}
    .code-preview {{
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px;
      font-family: var(--font-mono);
      font-size: 13px;
      overflow-x: auto;
      white-space: pre-wrap;
      color: #e2e8f0;
      max-height: 450px;
    }}
    .mcp-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
    }}
    @media (min-width: 768px) {{
      .mcp-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    .tool-list {{
      list-style: none;
      margin-top: 10px;
    }}
    .tool-list li {{
      padding: 8px 12px;
      background: #0b1120;
      margin-bottom: 8px;
      border-radius: 6px;
      border: 1px solid var(--border);
      font-size: 14px;
    }}
    .tool-list strong {{
      color: var(--primary);
      font-family: var(--font-mono);
    }}
    .copy-btn {{
      float: right;
      background: rgba(255, 255, 255, 0.1);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 12px;
      cursor: pointer;
    }}
    .copy-btn:hover {{ background: rgba(255, 255, 255, 0.2); }}
    .error-card {{
      border-color: var(--danger);
      background: rgba(239, 68, 68, 0.1);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <h1>WebLens</h1>
        <span class="badge online">Server Online</span>
        <span class="badge">v0.1.0</span>
      </div>
      <div>
        <span class="badge">Endpoint: /mcp</span>
        <span class="badge">Protocol: Streamable HTTP</span>
      </div>
    </header>

    <div class="card">
      <div class="tabs">
        <button class="tab-btn {'active' if action == 'search' else ''}" onclick="switchTab('search')">Web Search</button>
        <button class="tab-btn {'active' if action == 'extract' else ''}" onclick="switchTab('extract')">URL Extractor</button>
        <button class="tab-btn {'active' if action == 'research' else ''}" onclick="switchTab('research')">Deep Research</button>
        <button class="tab-btn {'active' if action == 'agent' else ''}" onclick="switchTab('agent')">AI Agent Connect</button>
      </div>

      <!-- Search Tab -->
      <div id="tab-search" style="display: {'block' if action == 'search' else 'none'};">
        <form method="GET" action="/">
          <input type="hidden" name="action" value="search" />
          <div class="form-group">
            <input type="text" name="q" class="form-input" placeholder="Search the web (multi-query consensus, domain authority)..." value="{_escape(q if action == 'search' else '')}" required />
            <button type="submit" class="btn">Search</button>
          </div>
        </form>
      </div>

      <!-- Extract Tab -->
      <div id="tab-extract" style="display: {'block' if action == 'extract' else 'none'};">
        <form method="GET" action="/">
          <input type="hidden" name="action" value="extract" />
          <div class="form-group">
            <input type="url" name="url" class="form-input" placeholder="https://example.com/article" value="{_escape(url if action == 'extract' else '')}" required />
            <button type="submit" class="btn">Extract</button>
          </div>
        </form>
      </div>

      <!-- Research Tab -->
      <div id="tab-research" style="display: {'block' if action == 'research' else 'none'};">
        <form method="GET" action="/">
          <input type="hidden" name="action" value="research" />
          <div class="form-group">
            <input type="text" name="q" class="form-input" placeholder="Topic to research with multi-hop synthesis..." value="{_escape(q if action == 'research' else '')}" required />
            <button type="submit" class="btn">Synthesize</button>
          </div>
        </form>
      </div>

      <!-- Agent Tab -->
      <div id="tab-agent" style="display: {'block' if action == 'agent' else 'none'};">
        <p style="margin-bottom: 12px; color: var(--text-muted);">
          WebLens exposes the complete web intelligence suite over Model Context Protocol (MCP) Streamable HTTP.
        </p>
        <div class="mcp-grid">
          <div>
            <h4>Claude Desktop & Cursor Configuration</h4>
            <div style="position: relative; margin-top: 8px;">
              <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('mcp-config-json').innerText); this.innerText='Copied!';">Copy</button>
              <pre id="mcp-config-json" class="code-preview">{_escape(claude_config)}</pre>
            </div>
          </div>
          <div>
            <h4>Exposed MCP Tools</h4>
            <ul class="tool-list">
              <li><strong>web_search</strong> &mdash; Multi-query consensus web search with scoring.</li>
              <li><strong>extract_url</strong> &mdash; Markdown extraction with code/table preservation.</li>
              <li><strong>web_map</strong> &mdash; Sitemap and link hierarchy discovery.</li>
              <li><strong>crawl_website</strong> &mdash; Deep website ingestion with semantic pruning.</li>
              <li><strong>deep_research</strong> &mdash; Autonomous multi-hop research with citations.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    {result_html}

    <div class="card" style="padding: 16px; font-size: 13px; color: var(--text-muted); display: flex; justify-content: space-between;">
      <span>MCP Endpoint: <code style="color: var(--primary);">{_escape(mcp_url)}</code></span>
      <span>JSON Healthcheck: <a href="/healthz" style="color: var(--primary);" target="_blank">/healthz</a></span>
    </div>
  </div>

  <script>
    function switchTab(name) {{
      ['search', 'extract', 'research', 'agent'].forEach(function(t) {{
        var el = document.getElementById('tab-' + t);
        if (el) el.style.display = (t === name) ? 'block' : 'none';
      }});
      var btns = document.querySelectorAll('.tab-btn');
      btns.forEach(function(b) {{
        b.classList.remove('active');
        if (b.getAttribute('onclick').indexOf(name) !== -1) b.classList.add('active');
      }});
    }}
  </script>
</body>
</html>"""


async def handle_demo_request(request: Request, service: Any) -> HTMLResponse:
    action = request.query_params.get("action", "").strip() or "search"
    q = request.query_params.get("q", "").strip()
    url = request.query_params.get("url", "").strip()

    result_data = None
    error_msg = None

    if action == "search" and q:
        try:
            result_data = await service.search(q, max_results=5)
        except Exception as exc:
            error_msg = f"Search failed: {exc}"
    elif action == "extract" and url:
        try:
            result_data = await service.extract(url)
        except Exception as exc:
            error_msg = f"Extraction failed: {exc}"
    elif action == "research" and q:
        try:
            result_data = await service.deep_research(q, max_tokens=1000)
        except Exception as exc:
            error_msg = f"Deep research failed: {exc}"

    host = request.headers.get("host") or "unkown0022-weblens.hf.space"
    html_output = _build_html(
        action=action,
        q=q,
        url=url,
        result=result_data,
        error=error_msg,
        host=host,
    )
    return HTMLResponse(html_output)
