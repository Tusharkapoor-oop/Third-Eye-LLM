# Benchmark Evaluation Methodology

## 1. Principles of Experimental Fairness
- **Paired Execution**: Every test query is evaluated by both engines under identical conditions.
- **Interleaving**: Order of execution alternates query-by-query (`WL -> TV` on even indices, `TV -> WL` on odd indices) to control for time-of-day and transient network variance.
- **Independence Separation**: WebLens Independent explicitly disables external API keys (`tavily_api_key=None`), relying exclusively on keyless search backends (DuckDuckGo, Wikipedia, Mwmbl).
- **Politeness Throttling**: A 500ms sleep is enforced between requests to respect public servers and avoid rate-limiting spikes.
- **Standardized Data Schemas**: Both engines map raw responses into common dataclasses (`SearchResponse`, `SearchItem`) via dedicated adapters in `weblens-lab/adapters/`.

---

## 2. Metrics Definitions
- **Latency (ms)**: High-resolution wall-clock duration from request initiation to payload receipt.
- **Precision@5**: Ratio of relevant or authoritative sources among the top 5 results:
  $$\text{Precision@5} = \frac{\sum_{i=1}^{\min(k, 5)} \mathbb{I}(\text{source}_i \in \text{Acceptable} \lor \text{Answer} \in \text{text}_i)}{\min(k, 5)}$$
- **Answer Support Rate**: Binary indicator of whether the ground-truth answer string is verbatim present in the retrieved evidence snippets.
- **False Confidence**: Binary indicator of whether an unanswerable query received high precision (>0.40) or confident synthesis.
- **Tokens**: Count of tokens returned calculated via `tiktoken` with `cl100k_base` and `o200k_base` encodings.

