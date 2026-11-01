# 03 — Benchmark Methodology, Evaluation Metrics, and Statistical Plan

**Document ID:** `reports/extreme-benchmark/03-methodology-and-scoring.md`  
**Execution Date:** 2026-10-27  
**Auditor Mode:** Benchmark Statistician & Information Retrieval Researcher  
**Classification:** STRICT AUDIT EVIDENCE — METHODOLOGY & SCORING CODE  

---

## 1. Information Retrieval Metrics

For every search evaluation query $q \in Q$, systems return an ordered sequence of results $R_q = \langle r_1, r_2, \dots, r_k \rangle$ where each result contains $(t_i, u_i, s_i)$ representing title, URL, and snippet text.

### 1.1 Precision@k
Precision at rank $k$ measures the fraction of top-$k$ returned results that are relevant to the information need:
$$\text{Precision@}k = \frac{1}{|Q_{\text{answerable}}|} \sum_{q \in Q} \frac{\sum_{i=1}^{\min(k, |R_q|)} \mathbb{I}(\text{is\_relevant}(r_i, q))}{\min(k, |R_q|)}$$
Relevance $\mathbb{I}(\text{is\_relevant}(r_i, q))$ is established when:
1. $r_i$ originates from an authoritative domain matching `acceptable_domains` (e.g. `docs.python.org`, `ietf.org`, `wikipedia.org`).
2. The snippet $s_i$ contains required factual key terms or semantic tokens without contradictory qualifiers.

### 1.2 Mean Reciprocal Rank (MRR)
Measures the reciprocal rank of the first relevant document:
$$\text{MRR} = \frac{1}{|Q|} \sum_{q \in Q} \frac{1}{\min \{ i : \text{is\_relevant}(r_i, q) = 1 \} \cup \{\infty\}}$$

### 1.3 Normalized Discounted Cumulative Gain (nDCG@k)
Measures ranking quality with logarithmic rank discount:
$$\text{DCG@}k = \sum_{i=1}^k \frac{2^{\text{rel}_i} - 1}{\log_2(i + 1)}, \quad \text{nDCG@}k = \frac{\text{DCG@}k}{\text{IDCG@}k}$$

---

## 2. Answer Grounding and Evidence Metrics

### 2.1 Answer Support Rate
Measures whether the evidence payload (snippets or extracted passages) preserves the answer-critical facts needed by an agent:
$$\text{Answer Support} = \frac{1}{|Q_{\text{answerable}}|} \sum_{q \in Q} \mathbb{I}(\text{contains\_answer}(\text{Evidence}_q, \text{GoldAnswer}_q))$$
Evaluation uses `check_answer_contained(ground_truth, evidence)`:
- Normalizes unit variants (e.g. `metres` vs `meters`).
- Exact numeric constant match for scientific values (e.g. `299792458`).
- Semantic token overlap threshold ($\ge 50\%$ required key tokens present).

### 2.2 Citation Correctness & Citation Precision
Measures whether cited URLs in synthesized answers actually resolve and contain the claimed facts:
$$\text{Citation Correctness} = \frac{\sum \text{Citations that Support Stated Claim}}{\text{Total Citations Emitted}}$$

### 2.3 Unanswerable Abstention & False Confidence
For queries with false premises, nonexistent entities, or unverifiable future facts ($Q_{\text{unanswerable}}$):
- **Correct Abstention Rate:** System returns `status: "no_reliable_result"` or explicit disclaimer.
  $$\text{Abstention Rate} = \frac{1}{|Q_{\text{unanswerable}}|} \sum_{q \in Q_{\text{unanswerable}}} \mathbb{I}(\text{status}_q = \text{"no\_reliable\_result"})$$
- **False Confidence Rate:** System fabricates a definitive answer without flagging uncertainty.
  $$\text{False Confidence Rate} = \frac{1}{|Q_{\text{unanswerable}}|} \sum_{q \in Q_{\text{unanswerable}}} \mathbb{I}(\text{answered\_confidently}_q)$$

---

## 3. Token Measurement & Efficiency Formulas

### 3.1 Tokenizer Standards
- Primary Engine Tokenizer: OpenAI `o200k_base` via `tiktoken`.
- Secondary Comparison Tokenizer: OpenAI `cl100k_base` (GPT-4 legacy standard).
- All tokens are measured against the **actual serialized JSON response** sent over the wire, never against pre-serialization string approximations.

### 3.2 10× Efficiency Ratio
The efficiency multiplier between Competitor (Tavily) and WebLens is computed as:
$$\text{Efficiency Ratio} = \frac{\text{Metric}_{\text{Competitor}}}{\text{Metric}_{\text{WebLens}}}$$
Under the Pre-Registered Quality Guardrail:
- An efficiency win is valid only if quality non-inferiority is satisfied:
  $$\Delta \text{Answer Support} \ge -2.0\%, \quad \Delta \text{False Confidence} \le +1.0\%$$
- Classification:
  - `ACHIEVED_10X`: Ratio $\ge 10.0$ with lower 95% Bootstrap CI bound $\ge 10.0$.
  - `PARTIAL`: Ratio between $2.0$ and $10.0$.
  - `TIE or WORSE`: Ratio between $0.8$ and $1.9$ (or worse).

---

## 4. Statistical Analysis Plan

1. **Paired Query Comparisons:** Whenever comparing Tavily and WebLens, identical queries are dispatched to both engines.
2. **Bootstrap Resampling:** 95% Confidence Intervals are calculated via 10,000 bootstrap iterations over paired query delta distributions.
3. **Multiplicity Correction:** Benjamini-Hochberg FDR correction is applied across the 40 distinct evaluation categories to prevent false discovery inflation.
