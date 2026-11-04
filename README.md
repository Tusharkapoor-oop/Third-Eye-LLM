# WebLens: Web Intelligence Platform & Model Context Protocol (MCP)

WebLens is a local-first, cloud-deployable web intelligence platform for AI agents. It provides compact, citable evidence packets, bounded crawling, a local RAG knowledge base, and nine application workflows over a real MCP server.

This README reports **measured** results from the current V10 evaluation. It deliberately does not repeat older unverified marketing numbers.

---

## Live Cloud Deployment

- **MCP endpoint:** `https://weblens-fgunqcnrla-uc.a.run.app/mcp`
- **Alias endpoint:** `https://weblens-16131012091.us-central1.run.app/mcp`
- **Health/root:** `GET /` returns `{"status":"ok","service":"weblens","version":"0.1.0","mcp_endpoint":"/mcp"}`
- **Current revision:** `weblens-00006-l9h` (region `us-central1`)
- **Transport:** JSON-RPC over Streamable HTTP MCP
- **Public tool surface:** 10 stateless tools. The three stateful tools (`crawl2rag_index`, `crawl2rag_query`, `research_chat`) are **not** registered on the public unauthenticated listener because they share a process-wide SQLite store.
- **Local tool surface:** all 13 tools under `--profile full` on loopback (or with a bearer token).

The deployment is public (`allUsers`). Authentication is **not enforced**, and no application-level rate limit was observed. See the security section below.

---

## V10 Three-System Measurement (120 queries)

Dataset: `weblens-lab/datasets/eval_benchmark_suite_v10.json` (`v10.0.0`), 120 curated queries, 30 categories × 4, 60 dev / 60 held-out, SHA-256 `a42d4004fb91208f1ae18de89e2337f2ccf5e7cb580a3c600a8ec7d8057d6361`.

Systems measured independently, same queries, no merged results:

1. Local WebLens MCP server process (`python -m weblens.cli serve --http --profile full`, keyless providers only)
2. Deployed WebLens MCP (`weblens-00003-l9q` at measurement time; current revision has remediation changes)
3. Tavily direct `/search` (`search_depth=basic`, 5 results)

| Metric | Local WebLens | Deployed WebLens | Tavily |
|---|---:|---:|---:|
| Graded queries | 107 | 107 | 107 |
| Success rate | 0.900 | 0.942 | 1.000 |
| p50 latency | **837.0 ms** | 1,037.8 ms | 1,537.4 ms |
| p95 latency | **1,497.3 ms** | 1,622.2 ms | 2,673.1 ms |
| P@5 | 0.553 | 0.471 | **0.740** |
| nDCG@5 | 0.669 | 0.729 | **0.777** |
| Hit@5 | 0.729 | 0.832 | **0.935** |
| Mean tokens (`cl100k`) | **182.3** | 206.2 | 1,378.7 |
| Provider credits | 0 | 0 | 120 |

95% CIs for P@5: local `[0.484, 0.624]`, deployed `[0.411, 0.533]`, Tavily `[0.675, 0.804]`.

**Honest reading:** WebLens is ~1.8× faster and returns ~7.5× fewer tokens than Tavily, but Tavily is more relevant and more reliable on this dataset. Paired local−Tavily P@5 is **−0.187**, 95% CI `[−0.265, −0.108]` (24 wins / 34 ties / 49 losses). Do not claim WebLens beats Tavily on retrieval quality.

Full report: `reports/three-system-comparison-v10/V10_REPORT.md`.

### Dataset status

- 120 curated queries achieved.
- 100k primary / 250k preferred / 500k stress targets: **BLOCKED**, not met.
- 10k adversarial cases: **BLOCKED**; 9 curated cases exist.
- 13 unanswerable/ambiguous/contradictory queries are excluded from graded metrics (107 graded).

---

## Official Tavily Demo Use-Case Coverage

All eight official Tavily demo use cases were exercised through real WebLens tools, with Tavily `/search` as a retrieval baseline:

| ID | Use case | WebLens tool | WebLens facet coverage | Tavily facet coverage |
|---|---|---|---:|---:|
| UC-01 | Company research | `company_research` | 0.25 | 0.75 |
| UC-02 | Financial market research | `market_research` | 0.25 | 1.00 |
| UC-03 | Web-powered assistant | `deep_research` | 0.50 | 1.00 |
| UC-04 | Compliance risk screening | `deep_research` | 0.00 | 0.75 |
| UC-05 | Sales meeting prep | `meeting_prep` | 0.50 | 0.75 |
| UC-06 | Supply chain risk | `deep_research` | 0.00 | 0.75 |
| UC-07 | Underwriting research | `deep_research` | 0.00 | 0.75 |
| UC-08 | Data enrichment | `sheets_enrich` | 0.60 | 1.00 |

Mean facet coverage: **WebLens 0.263 vs Tavily 0.844**. Mean tokens: **149.1 vs 1,278.6**. Mean latency: **9,102 ms vs 332 ms**. Scoring counts output evidence only; query/input echoes are excluded.

Caveat: Tavily `/search` returns snippets, not a synthesized report; this is a retrieval-only lower bound for Tavily, not a full agent comparison. Results: `reports/tavily-use-cases-v10/results.json`.

---

## Model Access (Not a Ranking)

| Model | Status | Evidence |
|---|---|---|
| `mistralai/mistral-large-4-1t-a52b` (NVIDIA) | **ACCESSIBLE** | HTTP 200, exact JSON reply, 21.4 s, 116 reasoning tokens |
| `openai/gpt-oss-20b` (NVIDIA) | **BLOCKED** | Two probes (60 s, 150 s) returned `ReadTimeout` |
| `nv-mistralai/mistral-nemo-12b-instruct` | **BLOCKED** | HTTP 404, not entitled for this account |
| “GPT-OSS 12B” | **UNSUPPORTED** | No such model ID available; 12B option is Mistral NeMo 12B |

Only one model produced a completion. A model-vs-model quality ranking would be fabricated and is not reported.

---

## Nine Product Applications

Verified live end-to-end: **9 PASS / 0 PARTIAL / 0 FAIL** (`reports/nine_applications_verification.json`).

1. Deep research with URL + exact span citations
2. Company researcher
3. Conversational answer engine
4. Crawl2RAG (real crawl → index → query, passage spans)
5. Market researcher / portfolio analyzer
6. Sheets batch enricher (formula injection defanged)
7. Meeting preparation agent
8. WebLens 101 tutorial (all 9 steps)
9. Persistent research chat (reopen and export)

Run: `python tools/run_all_nine_apps_live.py`

---

## Security Posture (Measured, Not Assumed)

**Local:** 38/38 checks pass (`reports/local-security/local_security_results_v2.json`). SSRF blocking works for metadata, loopback, RFC1918, IPv6 loopback and `file://`; a public control URL still extracts, proving the block is not blanket denial.

**Deployed (revision `00006-l9h`):** 18 PASS / 4 FAIL / 1 UNSUPPORTED (`reports/deployed-security/deployed_security_results_v2.json`).

Open findings:

- Unauthenticated MCP `initialize` succeeds, and a bogus `Bearer` token is accepted. The service is public.
- No application-level rate limit was observed in 20 cheap metadata calls. This was not a load test.
- No HSTS header on the app response.
- Cross-tenant isolation is **UNSUPPORTED**, not PASS: stateful tools were removed from the public listener after a real leak was found on revision `00005`. True multi-tenant isolation is not implemented.

Not claimed: “fully hardened”, “10/10 remote checks passed”, or “zero trust”. The old README claimed these; they are contradicted by the measured audit.

The deployment does **not** include `.env`; no API keys are baked into the image.

---

## MCP Client Configuration

### Deployed (public, stateless tools)

```json
{
  "mcpServers": {
    "weblens-cloud": {
      "url": "https://weblens-fgunqcnrla-uc.a.run.app/mcp"
    }
  }
}
```

### Local (all 13 tools)

```json
{
  "mcpServers": {
    "weblens-local": {
      "command": "python",
      "args": ["-m", "weblens.cli", "serve", "--profile", "full"],
      "env": {"WEBLENS_MCP_PROFILE": "full"}
    }
  }
}
```

---

## Installation & Local Execution

```bash
git clone https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git
cd Third-Eye-LLM
pip install -e ./weblens -e .
```

```bash
# stdio MCP server (all 13 tools)
python -m weblens.cli serve --profile full

# local HTTP MCP server
python -m weblens.cli serve --http --host 127.0.0.1 --port 8765 --profile full

# non-loopback without a token: stateful tools are disabled
python -m weblens.cli serve --http --host 0.0.0.0 --port 8080 --profile full --allow-insecure
```

### Application CLI

```bash
python -m weblens.cli app company "Anthropic"
python -m weblens.cli app market "Apple Inc."
python -m weblens.cli app market --portfolio "AAPL" --portfolio "MSFT"
python -m weblens.cli app meeting "Architecture Review" -a "Guido van Rossum" -c "Python Software Foundation"
python -m weblens.cli app tutorial --step all
```

---

## Tests Actually Executed

| Suite | Result |
|---|---|
| Targeted security/SSRF/crawler/extraction (`pytest tests/...`) | **170 passed** in 16.7 s |
| Injection + app lifecycle (`pytest tests/test_injection_sanitization.py weblens/tests/test_apps.py`) | **47 passed** in 21.1 s |
| MCP/auth/apps/config (`pytest weblens/tests/...`) | passed |
| Full root `pytest tests` | **INCOMPLETE**: reached ~93% then hung >15 min and was terminated; not reported as a pass |
| Nine apps live runner | **9/9 PASS** |
| Local security v2 | **38/38 PASS** |
| Deployed security v2 | **18 PASS / 4 FAIL / 1 UNSUPPORTED** |

---

## Repository Layout

- `weblens/src/weblens/` — canonical WebLens package (edit here)
- `src/weblens/` — editable-install mirror; must stay identical
- `weblens-lab/` — evaluation harness, dataset, security lab, adapters
- `reports/` — V10 analysis, use-case results, security results, nine-app evidence
- `evidence/` — claim ledger, experiment index, loop state, security findings
- `server.py` — legacy MyWebEngine demo; **not** the Cloud Run entry point

---

## Documentation

- [V10 three-system report](reports/three-system-comparison-v10/V10_REPORT.md)
- [Claim ledger](evidence/CLAIM_LEDGER.md)
- [Security findings](evidence/SECURITY-FINDINGS.md)
- [Experiment index](evidence/EXPERIMENT-INDEX.md)
- [Final A–L report](reports/FINAL_REPORT.md)
- [MCP API reference](docs/MCP_API_REFERENCE.md)
- [Security threat model](docs/SECURITY_THREAT_MODEL.md)
