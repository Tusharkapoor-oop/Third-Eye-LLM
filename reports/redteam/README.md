# Red-Team Reports

**Campaign:** `stage7-20261028-a4a64151`  
**Scope:** local WebLens code and owned loopback fixtures only  
**Result:** 40 controlled cases, 38 PASS, 2 FAIL, 0 critical/high

| File | Purpose |
|---|---|
| `00-scope-and-threat-model.md` | Authorization, in/out of scope, data flow, threats, status rules |
| `00-environment-fingerprint.json` | Host, Python, git, browser, secret-presence flags |
| `01-controlled-test-results.md` | Case-group results and the two retry failures |

Machine-readable results are in `../tavily-comparison/SECURITY-RESULTS.json`; raw evidence is in `../tavily-comparison/raw/security.jsonl`.

This is not a full penetration test, not an OS/container/browser sandbox audit, and not a full MCP conformance run. Prior claims of an unconditional pass are archived at `../_archive/prior-run-20261027/` and are not current evidence.
