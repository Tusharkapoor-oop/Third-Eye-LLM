# Evaluation Limitations & Threats to Validity

## 1. Sample Size
- The initial paired pilot comprised 18 stratified queries across 18 distinct categories. While stratified to cover all major failure modes, full statistical significance on subtle metrics requires scaling to 1,000+ queries.
- Scaling was intentionally bounded to 18 queries to conserve the user's billable Tavily credit allocation (consuming only 18.0 credits out of the 1,000 credit account allocation).

## 2. Dynamic Live Web Variance
- Web search results and latencies fluctuate based on public ISP routing, CDN caching, and third-party engine index updates.
- Repeated executions at different times of day may show variance of +/- 15% on public search provider response times.

## 3. Answer String Matching
- Answer support was evaluated using exact-case-insensitive string presence of the ground-truth answer in retrieved snippets.
- Paraphrased or semantically equivalent answers that did not contain the exact target token were conservatively scored as unsupported (`False`), slightly understating real human utility.

