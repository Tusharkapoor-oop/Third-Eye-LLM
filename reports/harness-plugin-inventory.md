# Harness capability & plugin inventory

**Purpose:** answer what the DeepSeek/Freebuff harness can actually import and drive in this repository, and where each extension point lives. Everything below was verified by reading the live code paths, not from memory.

**Date:** 2026-11-08 · **Commit:** `4e0885d` (working tree dirty)

---

## 1. Harness-level surfaces available to the agent

| Surface | What it provides | Availability |
|---|---|---|
| Tool calls | Shell execution, file read/edit/write, code search, glob, directory listing, browser fetch of URLs, web search, to-do tracking, user questions, UI buttons, service discovery (Gravity Index) | Always on |
| Skill catalog | Pre-loaded, loadable by name via the `skill` tool (accessibility, testing, security, framework guides, agent-design, ops, etc.) | Always on |
| `npx skills` CLI | Community skills: `npx skills find <query>`, `npx skills add <owner/repo> --skill <name> --yes` → installs into `.agents/skills/` | On demand |
| Sub-agent spawning | **Not available in this harness** — work that would be parallelised into "agents" runs as sequential role passes (see `.freebuff/agents/team.json`) | Not available |

**Honest limitation:** this project ships **no** vendored skills or plugin manifests — there is no `.agents/`, `.claude/`, `.codebuff/` or `.cursor/` directory. `.freebuff/` contained only `project-id`, and now contains `agents/team.json`. The skill catalog is runtime-provided by the harness, so its contents are not pinned by this repo.

## 2. Repository extension points (all importable / registrable)

| # | Extension point | Registration site | How to add one | Enablement |
|---|---|---|---|---|
| 1 | MCP tools | `server.py` — `@mcp.tool(name=...)` on async functions; base tools at lines 117-222, extended profile in `_register_extended_tools()` (line 224) | Define an async function returning a JSON string and decorate it | Base tools always; extended set via `WEBLENS_V14_EXTENDED_TOOLS=1` |
| 2 | Model providers | `model_provider.py` — `ModelProvider` StrEnum, `model_family()`, `model_readiness()`, `generate()` route chain | Add an enum member + route block; Qwen/Gemma already added (§3) | `NVIDIA_*_KEY`, `GEMINI_API_KEY`, `QWEN_*`, `GEMMA_*` |
| 3 | Search providers | `search_pipeline.py` — `_search_searxng()` (line 76), DuckDuckGo lite (line 120), aggregation in `search()` (line 301) | Add a `_search_<name>()` coroutine and append it to the task list in `search()` | `SEARXNG_BASE_URL`, `BRAVE_SEARCH_API_KEY`, `EXA_API_KEY`, keyless fallbacks |
| 4 | Extraction tiers | `extractor.py` — `TieredExtractor` (line 167), browser tier behind `ENABLE_BROWSER_FALLBACK` | Add a tier method and place it in the tier ladder | `ENABLE_BROWSER_FALLBACK`, `BROWSER_BINARY_PATH` |
| 5 | Reranking / chunking | `reranker.py` — `StructureAwareChunker` (line 29), `TwoStageReranker` (line 141) | Swap or extend the reranker class | Pure Python, no key |
| 6 | Applications | `weblens/src/weblens/apps/` — research chat, deep research, document export | Add an app module consuming `service.research` | Imported by the packaged lib |
| 7 | Agent team | `.freebuff/agents/team.json` + `scripts/agent_team.py` | Add a role with `commands` + `gate` | `python scripts/agent_team.py` |

## 3. Qwen and Gemma wiring (added this session)

| Model family | Route | Config | Current reachability |
|---|---|---|---|
| Qwen | Any OpenAI-compatible gateway (`/chat/completions`) | `QWEN_BASE_URL`, `QWEN_API_KEY` (or `DASHSCOPE_API_KEY`), `QWEN_MODEL` | **BLOCKED** — no key/gateway configured |
| Gemma | `GEMMA_BASE_URL` (defaults to the NVIDIA NIM host) | `GEMMA_MODEL` (default `google/gemma-4-31b-it`), `GEMMA_API_KEY` (falls back to the NVIDIA key) | **BLOCKED** — NVIDIA chat completions return `403 Authorization failed` |
| Mistral (NVIDIA) | NIM `/chat/completions` | `Mistral_Large_4_api_key_by_nividia` | **BLOCKED** — same `403` |
| Gemini | Google SDK, three-model fallback | `GEMINI_API_KEY` / `GEMINI_API_KEY_2` | **BLOCKED now** — free-tier daily quota (20 req) exhausted, retry in ~18 h; passed the full battery earlier today (`reports/cross-model/battery_20261108T185128.json`) |
| Local algorithmic | Deterministic synthesizer | none | Always available (fallback only, never counted as a model pass) |

A model is reported ready only when a credential exists; reachability is a separate live probe. The battery treats "answered by a different model" as BLOCKED, so a fallback can never masquerade as a Qwen/Gemma pass.

## 4. What "strict, top to bottom" means here

`scripts/cross_model_verification.py` walks every layer for each model:

1. credential → 2. live reachability (must be the *requested* model, not a fallback) → 3. exact-instruction, JSON contract, usage accounting, latency ceiling → 4. determinism at temperature 0 → 5. citation integrity (every source cited, no invented URLs) → 6. no fabricated sources on empty evidence → 7. engine end-to-end: `server.web_search` → `server.extract_url` → `synthesize_research_report` over the real extracted text.

Exit codes: `0` all pass, `1` a real failure, `2` nothing failed but at least one model was BLOCKED. There is no flag that turns a FAIL or BLOCKED into PASS, and no check is skipped for a reachable model.
