# V14 Extended MCP Profile

The root server now supports an opt-in extended profile:

```powershell
$env:WEBLENS_V14_EXTENDED_TOOLS='1'
.venv\Scripts\python.exe server.py
```

The default profile remains the original five-tool contract so existing schema
and token-tax clients are not broken. The extended profile registers:

- `browser_create_session`
- `browser_navigate`
- `browser_observe`
- `browser_interact`
- `browser_close_session`
- `geo_resolve`
- `generate_document`

The tool-list smoke returned all 12 names in the local process. Component tests
remain fixture/mock scoped: live geocoding, public browser navigation, deployed
MCP auth, and rendered document visual inspection are not claimed verified.
