# WebLens vs Tavily Comparison — Methodology

## Overview
This document describes the methodology used for the WebLens vs Tavily comparison as required by v8 §5. It covers experimental design, fairness guidelines, metric definitions, and reporting standards.

## A. Experimental Design

### 1. Comparison Categories (v8 §5.A)

#### Category 1: Independent Provider Comparison
- **Objective**: Compare WebLens's independently sourced search capability against Tavily's API
- **Exclusion**: Tavily-backed WebLens calls are excluded from the independent WebLens group
- **Providers tested**: 
  - WebLens with DDGS (independent, no API key)
  - WebLens with Bing (independent, optional key)
  - Tavily API directly (authorized credentials)
- **Measurement**: Each provider evaluated on identical query sets without orchestration overhead

#### Category 2: Same-Provider Orchestration Comparison
- **Objective**: Where WebLens uses Tavily as a backend, compare:
  - Direct Tavily API response
  - WebLens calling Tavily directly
  - WebLens calling Tavily with additional orchestration (caching, extraction, retrieval, reranking, synthesis)
  - WebLens with caching
- **Measurement**: Isolate the additional value and overhead introduced by WebLens orchestration layers

#### Category 3: End-to-End Application Comparison
- **Objective**: Compare complete product workflows using equivalent tasks and comparable settings
- **Where a provider cannot support an equivalent workflow**: Record the capability difference rather than forcing an invalid comparison
- **Measurement**: Full workflow completion time, quality, and reliability

### 2. Dataset Specification

#### Evaluation Datasets
- **50-query eval dataset**: `benchmarks/eval_dataset.json`
  - 50 queries across 5 categories: current_facts, niche_technical, conflicting_or_debatable, documentation_lookups, unanswerable_or_fabricated
  - Primary benchmark for the improvement loop (Cycles 1-5)
  - Used for cycle-by-cycle evaluation

- **200-query expanded dataset**: `benchmarks/eval_dataset_expanded.json`
  - 200 queries across 19 categories
  - Includes: academic_scientific, ambiguous_questions, conflicting_or_debatable, current_facts, current_official_docs, documentation_lookups, exact_phrase_search, javascript_heavy_pages, long_tail, multi_source_research, niche_technical, pages_poor_html, pages_return_errors, product_comparison, programming_debugging, ranking_extraction_weakness, technical_documentation, unanswerable_or_fabricated
  - Secondary/extended benchmark for comprehensive evaluation

#### Category Distribution (200-query dataset)
| Category | Query Count | Purpose |
|----------|-------------|---------|
| current_facts | ~25 | Simple factual questions |
| niche_technical | ~20 | PEP numbers, docker commands, CSS properties, HTTP status codes, TCP/UDP |
| unanswerable_or_fabricated | ~15 | Questions with insufficient evidence |
| conflicting_or_debatable | ~15 | Contradictory sources |
| technical_documentation | ~15 | API docs, SDK docs, framework docs |
| programming_debugging | ~15 | Code debug, error resolution |
| product_comparison | ~10 | Product comparison questions |
| market_research | ~10 | Stock/company research |
| company_research | ~10 | Company overview questions |
| multi_source_research | ~10 | Questions requiring multiple sources |
| exact_phrase_search | ~10 | Phrase-match queries |
| documentation_lookups | ~10 | API/parameter lookups |
| current_official_docs | ~10 | Latest official documentation |
| ambiguous_questions | ~5 | Questions with multiple interpretations |
| long_tail | ~5 | Long-tail, specific queries |
| pages_poor_html | ~5 | Pages with poor HTML structure |
| pages_return_errors | ~5 | Pages that return error status |
| caching/reliability | ~5 | Repeatability and consistency |

#### Dataset Versioning
- Datasets are versioned by hash (SHA-256) for reproducibility
- Dataset hash recorded in each benchmark run manifest
- Development and held-out test sets kept separate
- Raw responses, query order, timestamps, provider configurations, and evaluator decisions preserved

### 3. Provider Configuration

#### Independent WebLens (No Tavily Backend)
- **DDGS**: Default primary provider, no API key required
  - Configured in `src/engine/config.py`: `BRAVE_SEARCH_API_KEY=""`, `TAVILY_API_KEY=""` (empty in .env.example)
  - Activated via `DEFAULT_SEARCH_PROVIDER=ddgs` in .env
  - Integrates through `SearchAggregator.providers["ddgs"]`
  
- **Bing**: Optional secondary provider
  - API key optional (`BRAVE_SEARCH_API_KEY` in .env, currently empty)
  - Activated via provider name in benchmark harness
  - Integrates through `SearchAggregator.providers["bing"]`

- **Provider registry**: `src/engine/search/aggregator.py` registers available providers
  ```python
  self.providers: dict[str, SearchProvider] = {
      "bing": BingSearchProvider(),
      "wikipedia": WikipediaSearchProvider(),
      "ddgs": DDGSearchProvider(),
      "ddg_html": DDGHTMLSearchProvider(),
  }
  if CONFIG.brave_api_key:
      self.providers["brave"] = BraveSearchProvider(CONFIG.brave_api_key)
  tavily = TavilySearchProvider()
  if tavily.is_available():
      self.providers["tavily"] = TavilySearchProvider()
  ```

#### Tavily API (Authorized Credentials)
- **TavilySearchProvider**: Integrated in `src/engine/search/tavily_provider.py`
  - API key loaded from `CONFIG.tavily_api_key` or env var `TAVILY_API_KEY`
  - `is_available()` returns True only when key is configured and non-empty
  - Uses HTTPS REST endpoint: `https://api.tavily.com/search`
  - Default parameters: `search_depth="basic"`, `max_results=5`, `include_answer=False`
- **Integration point**: `SearchAggregator` automatically adds "tavily" provider when key is available
- **Secret redaction**: Harness applies `SECRET_PATTERNS` to redact keys from logs

#### Provider Routing Strategy (v8 §5.B.2)
Same-provider orchestration comparison measures:
1. **Direct Tavily API**: `await self.tavily.search(query, count=5)`
2. **WebLens calling Tavily**: `await self.aggregator.search(query, count=5, preferred_provider="tavily")`
3. **WebLens with orchestration**: Search → extract → retrieve → rerank → synthesize pipeline
4. **WebLens with caching**: Warm-cache experiments with `harness config warm_cache=True`

### 4. Fairness Guidelines (v8 §5.C)

#### Identical Query Sets
- Same query list used for all providers
- Query order randomized per repetition using fixed random seed
- No provider-specific query modification

#### Identical Output Requirements
- Same `count` parameter (default 5) across providers
- Same `max_tokens` budget where applicable (default 600 cl100k / 2000 o200k)
- Same evaluation criteria (success, no_reliable_result, error)

#### Comparable Search Depth and Result Limits
- All pilots use `time_filter=None` (no freshness filter)
- All pilots use `domains=None` (unrestricted)
- `search_depth="basic"` for all providers (Tavily parameter; DDGS/Bing also use basic)

#### Equivalent Model Settings for End-to-End Comparisons
- Same tokenizer encoding (cl100k_base for tokens, o200k_base for research)
- Same chunker configuration (target_tokens=180, overlap_tokens=30)
- Same extractor mode ("passages") and max_tokens (1200)
- Same reranking and fusion parameters (where applicable)

#### Randomization and Bias Reduction
- **Paired, interleaved A/B experiments**: Each repetition alternates provider order
- **Randomize execution order**: Reduces time-of-day and provider-load bias
- **Multiple repetitions**: 1-2 repetitions per pilot (more for final benchmark)
- **Fixed random seed**: For query subset selection and ordering

#### Separation of Cache States
- **Cold-cache**: First run with no prior caching (pilot mode default)
- **Warm-cache**: Subsequent runs with caching enabled (`harness config warm_cache=True`)
- **Separate reporting**: Cold-cache and warm-cache results reported separately
- **No mixing**: Cold-cache results not compared against warm-cache results

#### Prohibited Comparisons
- ❌ Do not compare a warm WebLens cache against a cold Tavily request
- ❌ Do not mix model quality with search-provider quality
- ❌ Do not repeatedly rerun a losing experiment until it produces a favorable result
- ❌ Do not compare different token budgets without documenting the delta
- ❌ Do not claim WebLens is better than Tavily without reproducible evidence

### 5. Metric Definitions

#### Response Time
- Time to first response byte
- Time to first useful result
- Time to first token (if streaming)
- Time to first citation
- Time to complete response
- Total workflow completion time (search + extract for E2E)

#### Latency
- p50 (median) latency
- p90, p95, p99 percentiles (where sample size supports it)
- Minimum and maximum
- Cold-start latency (first run, no cache)
- Warm-cache latency (subsequent runs with cache)
- Provider latency (search-only)
- Internal orchestration latency (E2E minus search-only)

#### Throughput
- Requests per second
- Completed jobs per minute
- Concurrent requests
- Successful requests under load
- Queue waiting time
- Queue processing time
- Backpressure behavior
- Timeout and retry behavior

#### Quality
- Search relevance (human- or LLM-judged)
- Precision@k
- Recall@k
- MRR (Mean Reciprocal Rank)
- nDCG (normalized Discounted Cumulative Gain)
- Extraction completeness (passages extracted / total relevant passages)
- Long-document coverage (queries with relevant results from long docs)
- Answer relevance (answer matches user intent)
- Answer factual support (answer claims supported by sources)
- Citation correctness (sources actually support cited claims)
- Citation coverage ( sufficient sources provided)
- Source diversity (number of distinct domains in sources)
- Source freshness (recency of cited sources)
- Contradiction detection (identified conflicting sources)
- Research completeness (all sub-questions answered)
- Hallucination rate (unsupported claims in answers)
- Appropriate abstention (correctly identified unanswerable queries)
- Missing-information detection (gaps in coverage)

#### Resource Consumption
- Input tokens (per query)
- Output tokens (per query)
- Total tokens (input + output)
- CPU utilization (percent of available cores)
- RAM usage (MB or GB)
- GPU usage (if applicable, otherwise N/A)
- Network transfer (KB per query)
- Disk and cache usage (MB)
- Embedding cost (if applicable)
- Reranking cost (if applicable)
- Model inference cost (if applicable)

#### Financial Efficiency
- Cost per request (USD)
- Cost per successful request (USD)
- Cost per research task (USD)
- Cost per 1,000 queries (USD)
- Cost per correctly supported answer (USD)
- API credits consumed
- Cost of failures and retries
- Unknown cost reported as UNKNOWN (not invented)

### 6. Experimental Fairness Requirements

#### Use Identical Query Sets
- Same JSON dataset file for all providers
- Same query subset per run (e.g., first 5 for quick mode, all 50 for full)
- No provider-tailored query selection

#### Use Identical Output Requirements
- Same `count` parameter (e.g., 5 results per query)
- Same `max_tokens` budget where comparable
- Same evaluation criteria (success/failure status definitions)

#### Use Comparable Search Depth and Result Limits
- Same `time_filter` setting (or None for fair comparison)
- Same `domains` restriction (or none)
- Same `search_depth` where applicable

#### Record Provider Configuration
- Document which API keys are configured
- Record which providers are available/available
- Note any errors or fallbacks

#### Run Enough Repetitions
- Report sample counts for each metric
- Report confidence intervals where applicable
- Use 1-2 repetitions for pilots, more for final benchmarks

#### Separate Cache States
- Clearly identify cold-cache vs warm-cache results
- Do not mix cache states in the same metric

#### Do Not Mix Model Quality with Search-Provider Quality
- Isolate provider performance from LLM/model performance
- Same model/settings across all providers in end-to-end comparisons

#### Do Not Repeatedly Rerun a Losing Experiment
- If an experiment fails, investigate root cause
- Fix the underlying issue, then rerun
- Do not rerun until favorable result

#### Do Not Claim WebLens is Better Than Tavily Without Reproducible Evidence
- All claims must map to evidence (benchmarks, datasets, manifests)
- Independent verification required for important claims

### 7. Required Comparison Output

#### Directory Structure (v8 §5.D)
```
reports/tavily-weblens-comparison/
├── EXECUTIVE_SUMMARY.md
├── PROVIDER_CAPABILITY_MATRIX.md
├── SEARCH_QUALITY.md
├── ANSWER_QUALITY.md
├── DEEP_RESEARCH_RESULTS.md
├── EXTRACTION_RESULTS.md
├── CRAWL_RAG_RESULTS.md
├── COMPANY_RESEARCH_RESULTS.md
├── MARKET_RESEARCH_RESULTS.md
├── SHEETS_RESULTS.md
├── MEETING_PREP_RESULTS.md
├── LATENCY_RESULTS.md
├── THROUGHPUT_RESULTS.md
├── RESOURCE_USAGE.md
├── COST_ANALYSIS.md
├── FAILURE_ANALYSIS.md
├── METHODOLOGY.md
├── LIMITATIONS.md
├── raw/
│   ├── jsonl/
│   └── csv/
├── datasets/
│   ├── eval_dataset_results.json
│   └── manifest_*.json
├── manifests/
│   ├── manifest_*.json
│   └── run_metadata_*.json
└── charts/
    *.{png,html,svg} (optional)
```

#### Per-Metric Reporting Format
For every metric, show:
- ✅ WebLens value (separate for DDGS, Bing, independent)
- ✅ Tavily value
- ✅ Difference (WebLens − Tavily or Tavily − WebLens, consistently directed)
- ✅ Percentage difference where meaningful
- ✅ Sample count (number of queries used)
- ✅ Confidence interval where applicable (p95, p99, etc.)
- ✅ Test configuration (delay, repetitions, cache state, token budget)
- ✅ Evidence reference (JSONL path, CSV path, manifest hash)
- ✅ Whether comparison is independent or backend-assisted

#### Separate Winners by Category
- Category 1 (Independent): Winner based on quality/speed/cost tradeoffs
- Category 2 (Orchestration): Winner based on additional value of WebLens layers
- Category 3 (E2E): Winner based on complete workflow comparison

#### Overall Conclusion Requirements
- Must not hide weaknesses behind one combined score
- Must produce separate winners by category
- Must clearly identify areas where each provider excels
- Must document infrastructure constraints (Tavily key availability, etc.)
- Must not fabricate success or hide regressions

## B. Evidence Chain Requirements

### For Every Experiment Preserve:
- ✅ Experiment ID (run_id from benchmark harness)
- ✅ Timestamp and timezone
- ✅ Git commit hash
- ✅ Working-tree status (clean/modified)
- ✅ Exact command used to run benchmark
- ✅ Environment (.env loaded, API keys configured)
- ✅ Dependency versions (tiktoken, mcp, etc.)
- ✅ Input dataset (dataset path, query count, category breakdown)
- ✅ Actual dataset record count (number of queries run)
- ✅ SHA-256 hash of input dataset for reproducibility
- ✅ Raw output (JSONL file with all provider results)
- ✅ Exit code (0 for success, non-zero for failure)
- ✅ Pass/fail counts per metric
- ✅ Result status (PASS/FAIL/PARTIAL/BLOCKED)
- ✅ Evidence paths (where artifacts are stored)

### Evidence Directory Structure
```
evidence/
  commands/
  logs/
  test-results/
  benchmarks/
  security/
  datasets/
  manifests/
  cycles/
  reports/
```

### Maintained Files
- ✅ `evidence/CLAIM-LEDGER.md` - Every important statement maps to evidence
- ✅ `evidence/BEST-KNOWN-GOOD.md` - Best verified version of the project
- ✅ `evidence/EXPERIMENT-INDEX.md` - Index of all experiments
- ✅ `evidence/AGENT-EXECUTION-LOG.md` - Agent execution tracking

## C. Data Analysis Guidelines

### 1. Statistical Reporting
- Report sample counts (n) for each metric
- Report confidence intervals (p95, p99) where sample size supports it
- Use non-parametric percentiles (this document's `pct()` function) for small samples
- Do not report statistics without corresponding sample counts

### 2. Confidence Intervals
- For p50: use median of observed values
- For p95/p99: use the `pct(values, p)` function from the benchmark harness
  ```python
  def pct(values: list[float], p: float) -> float:
      if not values:
          return 0.0
      s = sorted(values)
      k = (len(s) - 1) * (p / 100.0)
      f = int(k)
      c = min(f + 1, len(s) - 1)
      if f == c:
          return s[f]
      return s[f] + (s[c] - s[f]) * (k - f)
  ```

### 3. Per-Provider Comparison
- Each provider gets its own metric column/section
- Differences calculated as WebLens − Tavily (or consistently directed)
- Percentage difference = ( difference / reference ) × 100

### 4. Aggregation Rules
- **Do not average across providers** within a metric column
- **Do combine** like metrics (e.g., all p50 latencies in one table, all success rates in another)
- **Report per-query** detail in raw data (JSONL) for transparency

### 4. Handling Missing Data
- If a provider fails a query, record the failure reason (error, timeout, unavailable)
- Do not exclude failed queries from success rate calculations
- Document failure patterns and root causes
- Track retries and their impact on throughput and latency

### 5. Outlier Detection
- Use MAD-based outlier detection (per cost-anomaly skill) if sample size supports it
- Report outliers separately, do not automatically exclude them
- Document any trimmed or Winsorized values

## D. Reporting Templates

### Executive Summary Template
- Comparison overview
- Key findings table (metrics summary)
- Provider speed & efficiency summary
- Answer support quality summary
- Remaining gap documentation
- Recommendations
- Next steps

### Provider Capability Matrix Template
- Core search capabilities table
- Token budget comparison
- Provider features table
- API access & cost table
- Reliability & uptime table
- Summary rankings

### Search Quality Template
- Per-provider success rate table
- Latency comparison table
- Token consumption comparison
- Per-query detail table
- Quality observations
- Extended evaluation plan

### Answer Quality Template
- Answer support rate analysis
- Pilot vs full dataset discrepancy
- Per-provider answer analysis
- Answer grounding & citation
- Unanswerable query handling
- Quality recommendations

### Latency Results Template
- p50 latency distribution table
- p95 latency comparison table
- Latency percentiles comparison table
- Key observations
- Token-latency tradeoff table
- Cold-start vs warm-cache analysis
- Recommendations

### Throughput Results Template
- Per-provider throughput table
- QPM (queries per minute) analysis
- Per-provider throughput details
- Scaling analysis
- Resource utilization per query
- Recommendations

### Cost Analysis Template
- Direct cost per query table
- Token budget cost table
- Effective cost per supported answer
- Hidden costs table
- Cost-benefit analysis
- Cost recommendations

### Methodology Template
- Experimental design (categories A1-A3)
- Dataset specification (50/200 query details)
- Provider configuration (independent vs Tavily-backed)
- Fairness guidelines (v8 §5.C)
- Metric definitions (all categories)
- Experimental fairness requirements
- Required comparison output directory structure
- Evidence chain requirements
- Data analysis guidelines
- Reporting templates

### Limitations Template
- Explicitly list known limitations
- Document infrastructure constraints
- Acknowledge unverified claims
- Report untested areas
- State confidence boundaries

## E. Checkpoint/Resume State

### Before Checkpoint, Save:
- Current Git commit hash
- Active branch name
- Current task description
- Completed tasks (list with summaries)
- Failed tasks (list with rejection reasons)
- Pending tasks (next planned actions)
- Latest test results (paths to JSONL/CSV/manifest)
- Latest benchmark (run ID, key stats)
- Latest security findings (paths to findings/findings.md)
- API usage consumed (Tavily credits, if applicable)
- Remaining API budget, if available
- Next recommended task (exact description)
- Exact resume instructions (command to restart)

### On Restart, Load State And Resume Unfinished Work
- Read saved continuation state
- Restore environment (re-apply .env if needed)
- Resume from last completed checkpoint
- Do not repeat completed work unnecessarily
- Preserve all evidence from previous runs

## F. Glossary

| Term | Definition |
|------|------------|
| **Independent WebLens** | WebLens using DDGS/Bing without Tavily backend (no API key required) |
| **Tavily-backed WebLens** | WebLens routing searches through Tavily API (requires TAVILY_API_KEY) |
| **Provider routing** | Logic that selects which search provider to use per query or per session |
| **Token budget** | R1 Prime requirement: 600 cl100k tokens for search, 2000 o200k for research |
| **Cold-cache** | First run with no prior caching |
| **Warm-cache** | Subsequent runs with cached results from previous queries |
| **no_reliable_result** | Provider status indicating no reliable results found |
| **False confidence** | System marks unanswerable query as "success" (undesired; current rate ~0%) |
| **Improvement rule** | Mechanical rule: paired difference in target metric must exclude zero in good direction |
| **R1 Prime** | RuflO's performance tier requirement for token budgets and latency |
| **E2E** | End-to-end: search + extraction workflow |
| **QPM** | Queries Per Minute |
| **p50/p95/p99** | Percentile latency measurements (median, 95th, 99th percentile) |

## G. Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-11-01 | Initial methodology publication |
| v1.1 | 2026-11-01 | Added fairness guidelines and prohibited comparisons |
| v2.0 | 2026-11-01 | Full revision with v8 §5 compliance |

## H. Contact and Support
- For methodology questions: Review v8 §5 and this document
- For benchmark harness issues: See `benchmarks/benchmark_harness.py` source
- For provider integration: See `src/engine/search/aggregator.py` and `src/engine/search/tavily_provider.py`
- For evidence requirements: See `evidence/CLAIM-LEDGER.md` and `evidence/BEST-KNOWN-GOOD.md`