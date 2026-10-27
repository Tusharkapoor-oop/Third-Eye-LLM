# Client setup

WebLens speaks MCP over stdio by default. The same stdio command works in Roo
Code, Cline, Continue, Claude Desktop, and other MCP clients that accept a
command plus arguments.

Use an **absolute** path. Replace the example path with the location of this
`weblens` directory.

## Roo Code and Cline

Both clients use an `mcpServers` object in their MCP settings JSON. Open the
client's MCP settings UI and paste:

```json
{
  "mcpServers": {
    "weblens": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\Users\\ACER\\Downloads\\Broswer for ai agnets\\weblens",
        "weblens",
        "serve"
      ],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

If `uv` is not on the client's PATH, use the absolute `uv.exe` path reported by
`Get-Command uv` in PowerShell. Some client versions call the approval field
`alwaysAllow` instead of `autoApprove`; either is optional, and leaving it empty
means every tool call needs approval.

After saving, reload the MCP servers. The client should list four tools:
`web_search`, `extract_url`, `crawl_site`, `deep_research`.

## Continue

Add to Continue's `config.yaml` (newer versions use a list under `mcpServers`):

```yaml
mcpServers:
  - name: weblens
    command: uv
    args:
      - run
      - --directory
      - C:/Users/ACER/Downloads/Broswer for ai agnets/weblens
      - weblens
      - serve
```

Forward slashes are valid on Windows and avoid YAML escaping. If your Continue
version expects JSON instead, use the Roo/Cline object above.

## Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "weblens": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\Users\\ACER\\Downloads\\Broswer for ai agnets\\weblens",
        "weblens",
        "serve"
      ]
    }
  }
}
```

Fully quit and restart Claude Desktop; reloading the window is not always
enough.

## HTTP transport

Start the server once:

```powershell
uv run weblens serve --http --port 8765
```

The endpoint is `http://127.0.0.1:8765/mcp`. Clients that accept a URL:

```json
{
  "mcpServers": {
    "weblens": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

With a bearer token:

```powershell
uv run weblens serve --http --port 8765 --token "replace-me"
```

```json
{
  "mcpServers": {
    "weblens": {
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer replace-me"
      }
    }
  }
}
```

HTTP is stateless by default. Pass `--stateful` only for a legacy client that
requires `Mcp-Session-Id`. Binding a non-loopback address without a token is
refused unless `--allow-insecure` is passed; do not use that outside an
isolated machine.

## Smoke test without a client

```powershell
uv run weblens doctor --live --pretty
uv run weblens tokens --pretty
```

`doctor` reports provider availability and cache statistics. `tokens` reports
the measured `cl100k_base` schema size and whether it is within the 1,000-token
budget.

## Provider keys

Put `WEBLENS_TAVILY_API_KEY` and/or `WEBLENS_BRAVE_API_KEY` in
`weblens/.env`. The file is gitignored. The MCP command above uses
`--directory` to make `weblens` the working directory, so the server reads that
file; if you start the server from elsewhere, either pass `--directory` or set
the variables in the client's environment. A key alone does not enable a
provider: add `tavily` or `brave` to `WEBLENS_SEARCH_PROVIDERS`.

Never put a real key in `examples/clients/*.json`, `.env.template`, or a shell
script that is committed.

## Troubleshooting

- **Server exits immediately:** run `uv run weblens doctor` in the same shell.
  A configuration error is printed to stderr.
- **`uv` not found:** configure the absolute `uv.exe` path in the client.
- **All searches fail:** DuckDuckGo Lite may be throttling the IP. Try
  `WEBLENS_SEARCH_PROVIDERS=mwmbl,wikipedia`, or configure Brave/Tavily.
- **Non-ASCII is garbled:** the CLI forces UTF-8 on stdout, but the client's
  console encoding can still matter. Prefer the JSON output and `--pretty` only
  for terminals.
- **A tool returns `no_reliable_result`:** this is an evidence state, not a
  transport error. Read `gaps` and `warn` before retrying.
