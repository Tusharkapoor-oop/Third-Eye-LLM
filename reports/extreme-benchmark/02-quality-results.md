# Extreme-Scale Equivalent — Quality Results

**Scale:** 108 frozen queries, 81 dev / 27 sealed test  
**Systems:** Direct Tavily, WebLens keyless, WebLens-Tavily  
**Full evidence:** `../tavily-comparison/QUALITY-RESULTS.json`

This is the quality component of the 108-query equivalent. It is not a 500- or 10,000-query result.

---

## 1. Sealed test

27 queries, 17 answerable.

| Metric | Direct Tavily | WebLens keyless | WebLens-Tavily |
|---|---:|---:|---:|
| Search precision@5 | **0.2706** | 0.0588 | **0.2706** |
| Search hit@5 | **0.7647** | 0.2941 | **0.7647** |
| Search support | **1.0000** | 0.5294 | **1.0000** |
| Research support | — | 0.5294 | **0.9412** |
| No-result accuracy | — | 0.4000 | **0.8000** |
| False confidence | — | 0.6000 | **0.2000** |
| Conflict recall | — | 0.0000 | 0.0000 |

Status distribution:

- Direct Tavily: 27 `ok`.
- WebLens keyless: 22 `partial`, 5 `no_reliable_result`.
- WebLens-Tavily: 27 `ok`.

The keyless sealed-test precision collapse (`0.0588`) is the most important quality result. It is not a small-sample tie; it is a large gap on the only untouched split.

---

## 2. Combined

70 answerable queries.

| Metric | Direct Tavily | WebLens keyless | WebLens-Tavily |
|---|---:|---:|---:|
| Precision@5 | **0.2571** | 0.1686 | 0.2429 |
| Support | 0.9714 | 0.6714 | **0.9857** |
| Research support | — | 0.7857 | **0.9143** |
| Mean search latency | 1,637.3 ms | **886.8 ms** | 901.1 ms |
| Mean search payload tokens | 1,034.1 | **505.3** | 891.2 |

Paired direct-minus-keyless:

- Precision@5: `+0.0886`, 95% CI `[0.0257, 0.1486]`.
- Support: `+0.3000`, 95% CI `[0.1857, 0.4143]`.
- Latency: keyless faster by `750.5 ms`, CI `[580.1, 906.9]`.
- Payload tokens: keyless `528.7` fewer, CI `[455.0, 604.1]`.

WebLens-Tavily vs keyless research support: `+0.1286`, 95% CI `[0.0143, 0.2429]`, but WebLens-Tavily is `929.4 ms` slower on paired answerable rows (`n=70`).

---

## 3. Category signals

| Category | Rows | Direct precision@5 | Keyless precision@5 | WebLens-Tavily precision@5 | Keyless research support | WebLens-Tavily research support |
|---|---:|---:|---:|---:|---:|---:|
| docs | 28 | 0.2071 | 0.1357 | 0.2071 | 0.8214 | 0.9286 |
| niche_technical | 22 | 0.2455 | 0.1909 | 0.2636 | 0.8182 | 1.0000 |
| current_facts | 20 | 0.3400 | 0.1900 | 0.2700 | 0.7000 | 0.8000 |
| unanswerable | 20 | — | — | — | — | — |
| conflicting | 18 | — | — | — | — | — |

Conflict recall (separate metric, all 18 rows): keyless `0.0000`; WebLens-Tavily `0.0000`. Research support is `null` for the conflict category because those rows are not answerable in the support sense. All 18 conflict rows were measured; none was recalled.

Keyless is weakest on `current_facts` (`0.19` precision@5, `0.70` research support). It is closest on `niche_technical` search but still below direct Tavily.

---

## 4. Conflict and abstention

### Conflict

- Numeric: `0/8`.
- Conceptual: `0/10`.
- Overall: `0/18` (`0.0`).

No conflict query produced `conflicting_sources` or named the conflicting values. This blocks any contradiction-detection claim.

### Unanswerable

- 20 unanswerable rows total.
- Combined no-result accuracy: keyless `0.55`, WebLens-Tavily `0.65`.
- Combined false confidence: keyless `0.45`, WebLens-Tavily `0.35`.
- Sealed test: keyless `0.60` false confidence; WebLens-Tavily `0.20`.

Abstention is not reliable, especially for keyless.

---

## 5. Extraction

Ten targets.

| Variant | Status | Support | Mean latency | Mean text tokens |
|---|---|---:|---:|---:|
| Direct Tavily | 10 `ok` | 1.0 | 1,223.8 ms | 12,214 |
| WebLens full | 8 `ok`, 2 `error` | 0.7 | 5,370.1 ms | 2,421 |
| WebLens query-focused | 6 `ok`, 2 `error`, 1 `no_reliable_result`, 1 `possibly_outdated` | 0.7 | 3,644.4 ms | 433 |

The two full errors are SitePoint HTTP 403 and a Reddit JavaScript-only page. The token reduction is real, but it comes with lower support and two hard failures.

---

## 6. Verdict

- Direct Tavily wins search precision and support.
- Keyless wins speed and payload tokens, not quality.
- WebLens-Tavily recovers direct-quality search on the test split and improves research, but is Tavily-backed.
- Conflict recall is zero.
- Abstention is unreliable.
- Extraction is not equivalent.

No quality claim beyond these measured statements is supported.
