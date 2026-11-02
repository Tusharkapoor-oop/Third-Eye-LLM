# WebLens Quality Evaluation Methodology

## 1. Evaluation Philosophy

WebLens rejects vanity metrics, self-serving benchmarks, and ungrounded LLM-as-a-judge scoring. Evaluation is anchored on deterministic, reproducible, item-level pass/fail criteria across a rigorously stratified test corpus.

A system does not pass because its mean score looks acceptable. A quality gate passes only when every item in the verification battery satisfies its cryptographic, factual, and latency constraints.

---

## 2. Benchmark Dataset Structure (`eval_dataset_expanded.json`)

The primary evaluation suite comprises 100 to 200 curated, verified query benchmarks (SHA-256 `6130548dacb595da44a0973e66c4e3a44836846baf16a97ef1ca87664f2d065f`), stratified across nine distinct functional categories:

1. **Factual Verification:** Exact numerical, historical, or scientific truths with discrete ground truth answers (e.g. chemical formulas, atomic weights, launch years).
2. **Current Dynamic Information:** Time-sensitive statistics (e.g. current census data, interest rates, macroeconomic indices) designated as dynamic facts with source whitelists.
3. **Technical & API Documentation:** Concrete software engineering questions requiring exact library versions, syntax examples, or algorithmic behaviors.
4. **Comparative Analysis:** Objective multi-entity comparisons (e.g. `asyncio vs threading`, `PostgreSQL vs MySQL`).
5. **Entity Identification:** Company leadership, headquarters, official domains, and regulatory filings.
6. **False-Premise & Trap Queries:** Deliberately engineered unanswerable queries (e.g. `Python 4.0 release date`, `Mars Colony One 1982 expedition`, `Windows 14 architecture`).
7. **Adversarial & Indirect Injections:** Queries embedding instructions to leak secrets, override system instructions, or transmit canary tokens.
8. **Structured Tabular Data:** Multi-row data points requiring clean CSV/tabular extraction.
9. **Crawler Stress & Traps:** Target domains containing calendar infinite loops, deep directory mirrors, and gzip/zip bombs.

---

## 3. Metrics & Mathematical Definitions

### 3.1 Precision at Rank K ($P@K$)
Measures the proportion of retrieved results in the top-$K$ candidates that originate from acceptable authoritative domains or contain verifiable ground-truth evidence:

$$P@K = \frac{1}{K} \sum_{i=1}^{K} \mathbb{I}(\text{hit}_i \text{ is acceptable or contains evidence})$$

### 3.2 Answer Support Rate (ASR)
A binary metric per query indicating whether the top retrieved passages collectively contain the necessary tokens or institutional verification to support the true answer:

$$\text{ASR} = \frac{1}{N} \sum_{j=1}^{N} \mathbb{I}(\text{query}_j \text{ contains verifiable answer tokens})$$

- For symbolic / short tokens ($\le 3$ characters, e.g. `H2O`, `405`, `Au`, `@>`), evaluation requires exact non-alphanumeric token boundaries:
  $$\text{Pattern} = \verb|(?<![a-z0-9])| + \text{token} + \verb|(?![a-z0-9])|$$
- For dynamic facts (`NOT MEASURED -`), support is granted if and only if at least one top-5 result originates from a pre-registered authoritative institutional domain.

### 3.3 Abstention Accuracy (Trap Defense)
Evaluates whether the system correctly abstains on false-premise, fictional, or unanswerable queries:

$$\text{Abstention Accuracy} = \frac{\text{Correct Abstentions}}{\text{Total Trap Queries}}$$

Any assertion of confidence or generation of a synthetic answer on an unanswerable entity is scored as an immediate failure.

### 3.4 Citation Fidelity
Verifies that 100% of generated claims link to an exact character-span anchor (`char_start`, `char_end`) within the retrieved HTML document, and that the SHA-256 hash of the document matches the recorded ledger entry.

---

## 4. Four-System Benchmarking Protocol

To prevent bias, evaluations execute across four independently measured systems under identical conditions:

1. **System 1 (Local WebLens MCP):** The local MCP instance running on the development host (`http://127.0.0.1:50301/mcp`) using keyless consensus routing.
2. **System 2 (Deployed WebLens MCP):** The remote production deployment on Google Cloud Run (`https://weblens-16131012091.us-central1.run.app/mcp`).
3. **System 3 (Tavily Direct API):** The commercial Tavily API queried via official Python SDK endpoints.
4. **System 4 (Google Gemini API):** Gemini 2.5 Flash with native Google Search Grounding.

### 4.1 Independent Two-Run Verification
A quality field is declared PASS only after two consecutive, independent runs across the test suite yield identical 100% success without manual parameter tweaking or intermediate code modifications.

