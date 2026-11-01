# WebLens vs Tavily Comparison — Limitations

## Overview
This document explicitly lists the known limitations of the WebLens vs Tavily comparison as conducted in this session. Transparent reporting of limitations is a non-negotiable requirement (v8 §14: "Do not fabricate success. Do not hide regressions.")

## A. Infrastructure Constraints

### 1. Tavily API Key Availability
- **Limitation**: The Tavily API key is loaded from the session's `.env` file and may not be available in all environments
- **Impact**: Comparisons between independent WebLens (DDGS/Bing) and Tavily-backed operations are conditional on key availability
- **Evidence**: `TAVILY_API_KEY` is present in the session `.env` but may be absent in other deployments
- **Workaround**: Free providers (DDGS, Bing) work without any key; Tavily requires explicit key configuration
- **Severity**: High — enables/disables entire comparison categories

### 2. Hardware Limitations
- **Limitation**: RTX 3050 6GB VRAM, Intel Core 5 210H, 16GB RAM
- **Impact**: Performance measurements may differ on higher-/lower-spec hardware
- **Evidence**: Benchmark harness records platform in manifest (`reports/benchmark_runs/run_*.json`)
- **Workload**: CPU-bound search operations; GPU not heavily utilized in these pilots
- **Severity**: Medium — affects absolute latency/throughput numbers, not relative comparisons

### 3. Network Conditions
- **Limitation**: Internet connectivity to search providers (DDG, Bing, Tavily) via the host network
- **Impact**: Latency and success rates vary with network quality, ISP, and provider load
- **Evidence**: All pilots ran with 1.5s inter-query delay to avoid connection reset errors
- **Severity**: Medium — affects latency numbers but not token budget or quality metrics

## B. Pilot Study Limitations

### 1. Small Sample Size
- **Limitation**: Pilots used 5 queries per provider with 1 repetition each
- **Impact**: Results may not be representative of full query spectrum; statistical significance is limited
- **Evidence**: Quick mode (5 queries) vs full 50-query eval dataset produce different success rates (60% vs 70-83.3%)
- **Workload**: 5 queries × 3 providers × 1 repetition = 15 total runs per pilot
- **Severity**: High — limits generalizability; final benchmarks should use full datasets

### 2. Query Subset Selection
- **Limitation**: Quick mode uses first 5 queries from the dataset; not a random subset
- **Impact**: May bias results toward certain categories (e.g., current_facts over niche_technical)
- **Evidence**: Quick mode draws from `eval_dataset.json` first 5 entries; expanded dataset has 19 categories
- **Workaround**: Full benchmarks use all queries or stratified random subsets
- **Severity**: Medium — affects category-specific results

### 3. Single Repetition
- **Limitation**: 1 repetition per provider per pilot; no statistical variance measurement
- **Impact**: Cannot measure run-to-run variability or provider consistency
- **Evidence**: Previous cycles (1-5) observed variance; Cycle 3 rejected due to regression from variance
- **Workload**: 1 repetition means no paired difference calculation for 95% CI
- **Severity**: High — cannot establish statistical significance

### 4. Fixed Delay (1.5s)
- **Limitation**: Inter-query delay of 1.5s is hardcoded to avoid connection reset errors
- **Impact**: Throughput numbers are delay-limited; reducing delay may cause errors
- **Evidence**: Cycle 2-5 observed connection reset errors at lower delays; 1.5s is the established safe value
- **Workaround**: Experiments with 0.5s delay caused timeouts; 1.5s is the minimum stable value
- **Severity**: Medium — throughput is artificially limited; future work should find minimum stable delay

### 5. Cold-Cache Only (Pilot Mode)
- **Limitation**: Pilot data collected in cold-cache mode; no warm-cache experiments
- **Impact**: Throughput and latency may be better with cached results
- **Evidence**: Warm-cache flag available in harness but not enabled in pilots
- **Severity**: Medium — absolute numbers underestimate real-world performance with caching

## C. Comparison Limitations

### 1. Tavily Key Status Variable
- **Limitation**: Whether Tavily is "independent" or "backend-assisted" depends on key availability in the session environment
- **Impact**: Comparison categories must be explicitly labeled (independent vs Tavily-backed)
- **Evidence**: `TavilySearchProvider.is_available()` returns True/False based on key config
- **Severity**: High — comparison methodology must account for this variable

### 2. Free Provider Limitations
- **Limitation**: DDGS and Bing (free tier) have inherent limitations on niche technical questions
- **Impact**: ~30% of 50-query set consistently gets `no_reliable_result` for technical questions (PEP numbers, docker commands, CSS properties, HTTP status codes, TCP/UDP)
- **Evidence**: Improvement loop Cycles 1-5 documented this pattern; 83.3% max on technical-focused subset
- **Severity**: High — fundamental limitation of free search providers without Tavily credits

### 3. Token Budget Mismatch
- **Limitation**: Tavily's median 1348 tokens (cl100k) exceeds WebLens default search budget of 600
- **Impact**: Tavily-backed searches require either budget increase or token filtering
- **Evidence**: `DEFAULT_SEARCH_TOKEN_BUDGET=600` in config; Tavily returns 1348 median tokens
- **Workaround**: Increase budget to 2000 (deep research tier) or use query filtering
- **Severity**: High — affects cost and feasibility of Tavily integration

### 3. No Browser Automation
- **Limitation**: No browser automation (Playwright, Selenium) was used in these pilots
- **Impact**: Cannot compare web scraping/browser-based retrieval against Tavily's API-only approach
- **Evidence**: `ENABLE_BROWSER_FALLBACK=true` in config but not activated (headless browser not available)
- **Severity**: Medium — browser automation would be a separate integration

### 4. Single Hardware Platform
- **Limitation**: All benchmarks run on one machine (Intel Core 5 210H, RTX 3050 6GB, 16GB RAM)
- **Impact**: Results may not generalize to other hardware configurations
- **Evidence**: Manifest records `platform` field from `sys.platform` and hardware
- **Severity**: Medium — affects absolute numbers, not relative provider comparisons

## D. Unverified Claims

### 1. Tavily Superiority Claims
- **Claim**: "Tavily provides better answer support for niche technical questions"
- **Status**: UNVERIFIED in this session without Tavily Pro credits
- **Evidence**: Pilot data shows 80% success across all providers; Tavily's advantage only apparent with Pro tier
- **Severity**: Medium — requires Tavily Pro integration to verify

### 2. 100% Answer Support Claim
- **Claim**: "The improvement loop can reach 100% answer support rate"
- **Status**: BLOCKED by infrastructure constraint (no Tavily credits/browser automation)
- **Evidence**: Loop achieved 83.3% (Cycle 5); remaining gap documented as infrastructure-limited
- **Severity**: High — claim cannot be substantiated without Tavily/browser

### 3. Bing Equal to Tavily Quality
- **Claim**: "Bing performs equally well as Tavily for all query types"
- **Status**: UNVERIFIED — Bing is faster and more frugal but may have different quality characteristics
- **Evidence**: Pilot shows similar success rates (80%) but different token usage and latency profiles
- **Severity**: Medium — different query types may favor different providers

### 4. 60 QPM Sustained throughput
- **Claim**: "38 QPM can be sustained indefinitely with 1.5s delay"
- **Status**: PLausible but not verified over long runs
- **Evidence**: Based on 5-query pilot; sustained throughput may vary due to network fatigue, rate limits
- **Severity**: Low — operational guidance, not a quality claim

## E. Unexplored Areas

### 1. Full 50-Query Eval Benchmark
- **Status**: Not yet run (pilot used quick mode 5 queries)
- **Reason**: Time constraints (full 50 queries × 3 providers exceeds 2-minute timeout)
- **Plan**: Schedule full benchmark in next session

### 2. 200-Query Expanded Dataset
- **Status**: Dataset exists but not benchmarked
- **Reason**: Resource constraints (200 × 3 providers = 600 queries, significant time)
- **Plan**: Priority after pilot validation

### 3. Same-Provider Orchestration Comparison
- **Status**: Not yet executed (v8 §5.A.2)
- **Reason**: Requires WebLens Tavily-backend configuration; Tavily key available but not yet tested in orchestration mode
- **Plan**: Execute after core comparison complete

### 4. End-to-End (Search + Extract) Workflows
- **Status**: E2E mode available in harness but not yet run in comparison
- **Reason**: Would double experiment volume (search + extract per provider per query)
- **Plan**: Run after independent search comparison complete

### 5. Warm-Cache Experiments
- **Status**: Not enabled in these pilots
- **Reason**: Focus on cold-cache fairness; warm-cache requires separate benchmark run
- **Plan**: Execute as follow-up after cold-cache baseline established

### 6. Security Penetration Testing
- **Status**: Not yet performed (v8 §8)
- **Reason**: Core comparison and sandbox setup prioritized first
- **Plan**: Authorized red-team after comparison and product implementation

### 7. Nine Product Workflows Implementation
- **Status**: Not implemented (v8 §3)
- **Reason**: Comparison and sandbox prioritized; product workflows are separate major deliverable
- **Plan**: Separate workstream after comparison and infrastructure complete

### 8. Tavily Pricing Verification
- **Status**: Pricing tier assumed ($29-49/month Pro) but not verified via user dashboard
- **Impact**: Cost analysis may be inaccurate if actual pricing differs
- **Plan**: Verify via Tavily account before finalizing cost report

## F. Summary of Limitations

| Limitation | Severity | Impact |
|------------|----------|--------|
| Small pilot sample (5 queries) | High | Limited generalizability |
| No Tavily Pro integration | High | Cannot verify Tavily quality advantage |
| Token budget mismatch (1348 vs 600) | High | Affects Tavily feasibility |
| Free provider niche technical limitations | High | ~30% technical questions unsupported |
| 1.5s delay limits throughput | Medium | Throughput artificially capped |
| Cold-cache only (no warm-cache) | Medium | Absolute numbers underestimate real-world performance |
| Single hardware platform | Medium | Affects absolute numbers |
| Single hardware platform | Medium | Affects absolute numbers |
| Browser automation not used | Low | Separate integration needed |
| Tavily pricing not verified | Low | Cost estimates may change |
| Security testing not run | High (per v8) | Unexplored attack surface |

## G. Mitigation Plan

1. **Increase pilot sample size**: Run full 50-query benchmark in next session
2. **Integrate Tavily Pro**: Acquire/provision Tavily Pro credits to verify Tavily advantages
3. **Document infrastructure constraints**: Clearly label independent vs Tavily-backed comparisons
4. **Reduce delay to minimum stable value**: Test 0.5s/0.25s delays to find optimal balance
5. **Run warm-cache experiments**: Measure caching benefit and update throughput numbers
6. **Verify Tavily pricing**: Check user dashboard for actual per-key pricing
7. **Run security penetration testing**: Authorized red-team as required by v8 §8
8. **Implement nine product workflows**: Separate workstream after comparison complete
9. **Run 200-query expanded dataset**: Comprehensive category analysis
10. **Track evidence chain**: All results map to experiment IDs, dataset hashes, and manifest files

## H. Final Statement
All limitations are explicitly documented herein. No claims are made beyond what the evidence supports. The comparison demonstrates meaningful differences between providers (Bing fastest/frugal, Tavily comprehensive but key-required, DDGS key-free) but is constrained by:
- Pilot sample size (5 queries)
- Tavily key availability (development key only)
- Free provider technical limitations (niche questions)
- Token budget mismatch (Tavily 1348 > budget 600)
- Hardware and network conditions (single session environment)

Future work should address these limitations to produce a fully verified comparison. The current report should be treated as a pilot study, not a final evaluation.