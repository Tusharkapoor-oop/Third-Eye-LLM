# Extreme-Scale Dataset Audit

**Audited file:** `reports/_archive/prior-run-20261027/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl`  
**Whole-file SHA-256:** `d1d91fe1e7289affb0a85a0a412c6a9d47dbbde2ea5e994566dcd2aa1ba1c5ba`  
**Rows:** 10,000  
**Verdict:** **EXCLUDED — not valid ground truth**

---

## 1. What matches

- The whole-file hash matches the prior manifest’s `dataset_sha256`.
- Row count is 10,000.
- The file has 40 category names and a 6,000 / 2,000 / 2,000 split.

Those surface properties are not enough. The content does not support scoring.

---

## 2. Defects

### 2.1 Duplicate query text

- Rows: 10,000.
- Unique `query_text`: **5,528**.
- The manifest claims `total_unique_queries: 10000`.

The file therefore cannot support a 10,000-query unique benchmark.

### 2.2 Placeholder factual claims

Every row’s `required_factual_claims` is a generated ID, not a fact:

```json
"required_factual_claims": ["Claim-cat01_current_news-0"]
```

- Rows with placeholder-like claims: **10,000 / 10,000**.

A claim such as `Claim-cat01_current_news-0` cannot be used to judge answer support. Scoring against it would measure string matching against an opaque ID.

### 2.3 Generated query tokens

- Rows whose `query_text` contains `system_component_N`: **350**.
- Example: `global summit 2026 resolutions on system_component_0`.

These are template artifacts, not natural user queries.

### 2.4 Collapsed domain labels

- Distinct `acceptable_domains` sets: **2** across 10,000 rows.

The same five domains (for example `ietf.org`, `wikipedia.org`, `python.org`, `w3.org`, `nature.com`) are reused across unrelated categories. This destroys domain-label discriminative power.

### 2.5 Partition hashes do not reproduce

The manifest claims:

| Partition | Claimed hash |
|---|---|
| dev | `088af123d97bc79a9acd5eb433f53ea22f07c779ee1d3064f3e0e47403984341` |
| val | `f0ee6b334e150d68ad687fe46d82b1105c606e0cad793361c6508467e3c67ebe` |
| sealed_test | `16766e9a0b2519a919f6d36da9df5ed814fdd920cf4f921e0cef8349dfbf8346` |

Hashes computed from the actual partition lines:

| Partition | Computed hash |
|---|---|
| dev | `8552f71f6392f86b480ae1c1e8150d6619b5f71efb367b3d23c5041d0367e204` |
| val | `ae2fda052b688bb7935eb4d91723d4a75c38c37d91e306ef8c0732613041006b` |
| sealed_test | `87ab53376262c1000c867833f2512c16b7e6592d1bdfd0af6da925898298a4c4` |

The partition claims are not reproducible. The split cannot be treated as sealed or leak-free on this evidence.

---

## 3. Decision

The file is retained only in `reports/_archive/` for historical audit. It is not used in any quality, performance, cost, or security score.

The valid dataset is:

- `reports/tavily-comparison/data/stage7_dataset.jsonl`
- 108 rows, 5 categories, 81 dev / 27 sealed test.
- SHA-256 `a4a64151fbdbda850a9de128bb7f83ec67f126b633aac42488c6f0b9296a9b21`.

The 108-row dataset has its own limitations: small size, no human relevance judgments, and a preregistration timing violation. Those are disclosed in `../tavily-comparison/METHODOLOGY.md` and `PREREGISTRATION.json`.

---

## 4. Reproduce the audit

```powershell
cd "C:\Users\ACER\Downloads\Broswer for ai agnets"
@'
import json, hashlib
from collections import defaultdict
from pathlib import Path
p=Path('reports/_archive/prior-run-20261027/extreme-benchmark/datasets/extreme_benchmark_10k.jsonl')
rows=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
print('rows',len(rows),'unique_query_text',len({r['query_text'] for r in rows}))
print('placeholder_claims',sum(1 for r in rows if all(c.startswith('Claim-') for c in r['required_factual_claims'])))
print('system_component_rows',sum(1 for r in rows if 'system_component_' in r['query_text']))
print('distinct_domain_sets',len({tuple(r['acceptable_domains']) for r in rows}))
parts=defaultdict(list)
for line,r in zip(p.read_text(encoding='utf-8').splitlines(),rows):
    if line.strip(): parts[r['split']].append(line)
for k,v in parts.items():
    print(k,len(v),hashlib.sha256(('\n'.join(v)+'\n').encode()).hexdigest())
'@ | python -
```

Expected: 10,000 rows, 5,528 unique query texts, 10,000 placeholder claims, 350 generated-token rows, 2 domain sets, and the partition hashes above.
