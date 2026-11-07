"""Empirical Benchmark Analysis: WebLens Extraction vs Tavily Extract.
Quantifies:
1. Markdown cleanliness
2. Code block preservation
3. GFM tables
4. Noise removal
5. Token savings and compression percentage
6. Factual density (facts / 1k tokens)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import tiktoken

ENC = tiktoken.get_encoding("o200k_base")

def analyze():
    dataset_path = Path("reports/tavily-comparison/data/stage7_dataset.jsonl")
    dataset = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    qmap = {d["id"]: d for d in dataset}

    extraction_path = Path("reports/tavily-comparison/raw/extraction.jsonl")
    records = [json.loads(line) for line in extraction_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    NAV_PATTERNS = [
        r"\bcookie\b", r"\bsign in\b", r"\bsign up\b", r"\bprivacy policy\b",
        r"\bterms of service\b", r"\ball rights reserved\b", r"\bnewsletter\b",
        r"\badvertisement\b", r"\bnavigation\b", r"\bmenu\b", r"\bhome\b",
        r"\babout\b", r"\bsupport\b", r"\bjavascript:void\b"
    ]

    metrics = []

    for r in records:
        qid = r["query_id"]
        url = r["url"]
        qmeta = qmap.get(qid, {})
        answer_terms = qmeta.get("answer_terms", [])
        ground_truth = qmeta.get("ground_truth_answer", "")

        tav = r.get("tavily", {})
        tav_raw = tav.get("raw", {}).get("results", [{}])[0].get("raw_content", "") or ""
        tav_tok = tav.get("text_tokens", 0)
        tav_status = tav.get("status", "unknown")

        wf = r.get("weblens_full", {})
        wf_raw = wf.get("raw", {}).get("x", "") or ""
        wf_tok = wf.get("text_tokens", 0)
        wf_status = wf.get("status", "unknown")

        wq = r.get("weblens_query", {})
        wq_raw = wq.get("raw", {}).get("x", "") or ""
        wq_tok = wq.get("text_tokens", 0)
        wq_status = wq.get("status", "unknown")

        # Count facts (answer_terms hit in extracted text)
        tav_hits = sum(1 for term in answer_terms if term.lower() in tav_raw.lower())
        wf_hits = sum(1 for term in answer_terms if term.lower() in wf_raw.lower())
        wq_hits = sum(1 for term in answer_terms if term.lower() in wq_raw.lower())

        # Factual density = (hits / tokens) * 1000
        tav_density = (tav_hits / tav_tok * 1000) if tav_tok > 0 else 0.0
        wf_density = (wf_hits / wf_tok * 1000) if wf_tok > 0 else 0.0
        wq_density = (wq_hits / wq_tok * 1000) if wq_tok > 0 else 0.0

        # Noise count
        tav_noise = sum(len(re.findall(p, tav_raw, re.I)) for p in NAV_PATTERNS)
        wf_noise = sum(len(re.findall(p, wf_raw, re.I)) for p in NAV_PATTERNS)
        wq_noise = sum(len(re.findall(p, wq_raw, re.I)) for p in NAV_PATTERNS)

        # Code fences
        tav_code_count = len(re.findall(r"```", tav_raw)) // 2
        wf_code_count = len(re.findall(r"```", wf_raw)) // 2
        wq_code_count = len(re.findall(r"```", wq_raw)) // 2

        # HTML tag leak count
        tav_html_leaks = len(re.findall(r"<(?!(?:untrusted_source_content|/untrusted_source_content))[a-zA-Z][^>]*>", tav_raw))
        wf_html_leaks = len(re.findall(r"<(?!(?:untrusted_source_content|/untrusted_source_content))[a-zA-Z][^>]*>", wf_raw))
        wq_html_leaks = len(re.findall(r"<(?!(?:untrusted_source_content|/untrusted_source_content))[a-zA-Z][^>]*>", wq_raw))

        # Tables
        tav_table_delims = len(re.findall(r"\|[ -]+\|", tav_raw))
        wf_table_delims = len(re.findall(r"\|[ -]+\|", wf_raw))

        metrics.append({
            "qid": qid,
            "url": url,
            "terms": answer_terms,
            "tavily": {
                "status": tav_status,
                "tokens": tav_tok,
                "facts_recalled": tav_hits,
                "facts_density_per_1k": round(tav_density, 3),
                "noise_count": tav_noise,
                "code_fences": tav_code_count,
                "html_leaks": tav_html_leaks,
                "table_delims": tav_table_delims,
            },
            "weblens_full": {
                "status": wf_status,
                "tokens": wf_tok,
                "facts_recalled": wf_hits,
                "facts_density_per_1k": round(wf_density, 3),
                "noise_count": wf_noise,
                "code_fences": wf_code_count,
                "html_leaks": wf_html_leaks,
                "table_delims": wf_table_delims,
                "token_compression_pct": round((1 - wf_tok / tav_tok) * 100, 2) if tav_tok > 0 else 0.0,
            },
            "weblens_query": {
                "status": wq_status,
                "tokens": wq_tok,
                "facts_recalled": wq_hits,
                "facts_density_per_1k": round(wq_density, 3),
                "noise_count": wq_noise,
                "code_fences": wq_code_count,
                "html_leaks": wq_html_leaks,
                "token_compression_pct": round((1 - wq_tok / tav_tok) * 100, 2) if tav_tok > 0 else 0.0,
            }
        })

    return metrics

if __name__ == "__main__":
    m = analyze()
    print(json.dumps(m, indent=2))
