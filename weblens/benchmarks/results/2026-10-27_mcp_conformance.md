# MCP conformance run - 2026-10-27

Measured on Windows 11 with the official
`@modelcontextprotocol/conformance` suite.

## Run

| Field | Value |
| --- | --- |
| Suite | `@modelcontextprotocol/conformance` 0.1.16 |
| Mode | server, active suite |
| Server | `uv run weblens serve --http --host 127.0.0.1 --port 8765 --log-level warning` |
| URL | `http://127.0.0.1:8765/mcp` |
| Node | v24.19.0 |
| Date | 2026-10-27 |

```powershell
npx --yes @modelcontextprotocol/conformance@0.1.16 server `
  --url http://127.0.0.1:8765/mcp `
  --output-dir "$env:TEMP\weblens-conformance-2"
```

## Result

| Measure | Count |
| --- | --- |
| Scenarios run | 30 |
| Checks passed | 9 |
| Checks failed | 21 |
| Warnings | 1 |
| Scenarios fully passed | 8 |
| Scenarios failed | 21 |

The active suite is not filtered to the capabilities a server advertises. WebLens
declares only the `tools` capability. The 21 failures are scenarios that require
optional capabilities or the suite's fixture tools:

- `logging-set-level`, `completion-complete`
- `tools-call-image`, `tools-call-audio`, `tools-call-embedded-resource`,
  `tools-call-mixed-content`, `tools-call-with-logging`,
  `tools-call-with-progress`, `tools-call-sampling`,
  `tools-call-elicitation`
- `elicitation-sep1034-defaults`, `elicitation-sep1330-enums`
- `resources-read-text`, `resources-read-binary`, `resources-templates-read`,
  `resources-subscribe`, `resources-unsubscribe`
- `prompts-get-simple`, `prompts-get-with-args`,
  `prompts-get-embedded-resource`, `prompts-get-with-image`

Two passes are not evidence that WebLens's own tools were exercised:
`tools-call-simple-text` and `tools-call-error` pass when the server returns an
unknown-tool error. `resources-list` and `prompts-list` pass with empty lists.

The meaningful core for a tools-only server is the following, and all checks
passed:

| Scenario | Checks |
| --- | --- |
| `server-initialize` | 1/1 |
| `ping` | 1/1 |
| `tools-list` | 1/1, four tools |
| `dns-rebinding-protection` | 2/2, bad Host/Origin rejected with 421; loopback accepted |

`server-sse-multiple-streams` produced a warning because the default stateless
transport does not issue `Mcp-Session-Id`. That warning is expected for the
default configuration and is not counted as a failure.

## Runner issue on Windows

The Node CLI printed the complete results for every invocation, then exited with
a libuv assertion:

```text
Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), file src\win\async.c, line 94
```

The assertion is in the runner's Node process after `checks.json` was written; it
is not a WebLens response. It means the suite cannot currently be used as a
zero-exit CI gate on this Windows/Node combination without wrapping it or fixing
the runner. The check-level results above are from the saved `checks.json` files.

Raw scenario checks are in
[`2026-10-27_mcp_conformance.json`](2026-10-27_mcp_conformance.json).

## Scope

This run covers the Streamable HTTP transport and the advertised tools-only
surface. It does not cover stdio transport, tool-call semantics for the four
WebLens tools, OAuth, TLS termination, or client behavior. Those remain separate
gaps in `docs/PROTOCOL.md`.
