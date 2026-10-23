# Client config examples

These files are starting points, not universal configs. The absolute path in
each file points at this checkout; change it if you move the project.

- `claude-desktop.json` - merge the `mcpServers` object into
  `%APPDATA%\Claude\claude_desktop_config.json`.
- `roo-cline.json` - paste into the Roo Code or Cline MCP settings. The
  approval key is `autoApprove` in some versions and `alwaysAllow` in others;
  leaving the list empty requires approval for every call.
- `continue.yaml` - merge into Continue's `config.yaml`. Forward slashes avoid
  YAML escaping on Windows.
- `http-token.json` - for a client that accepts a URL and headers. Start the
  server with `uv run weblens serve --http --token "..."` and use the same token.

See [`../../docs/CLIENTS.md`](../../docs/CLIENTS.md) for details and
troubleshooting.
