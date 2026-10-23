# Architecture decision records

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-local-first-hybrid-providers.md) | Local-first service with keyless-default, pluggable providers | Accepted |
| [0002](0002-evidence-first-research.md) | Deterministic evidence research; no LLM synthesis | Accepted |
| [0003](0003-four-tool-mcp-surface.md) | Four read-only MCP tools; stateless HTTP default | Accepted |
| [0004](0004-token-budgets.md) | Hard token budgets on final serialized payloads | Accepted |
| [0005](0005-ssrf-connection-validation.md) | Connection-time IP validation for every fetch | Accepted |
| [0006](0006-lexical-passage-selection.md) | Lexical passage retrieval, no exposed score | Accepted |
| [0007](0007-bounded-crawl.md) | Bounded, robots-aware crawl/map | Accepted |
| [0008](0008-benchmark-gates.md) | Reproducible benchmark with hard, failing gates | Accepted |

ADRs record decisions and consequences, not proof that every target was met.
Measured gaps are in [`../LIMITATIONS.md`](../LIMITATIONS.md).
