"""Empirical search relevance and query planning benchmark script.
Evaluates query planning, parameter stripping, sub-query capping, stop-word removal,
domain authority weighting, retrieval precision, and source diversity on held-out queries.
"""
from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import urlparse

# Import engine components
from src.engine.query_engine import optimize_query, lexical_locks, _tokens, _STOPWORDS, _FILLER, _rule_plan
from src.engine.search.aggregator import (
    SearchAggregator,
    normalize_url as engine_normalize_url,
    authority_score as engine_authority_score,
    authority_tier as engine_authority_tier,
    get_domain,
)
from search_pipeline import (
    normalize_url as pipeline_normalize_url,
    calculate_domain_authority as pipeline_domain_authority,
)
import query_engine as root_query_engine
from src.weblens.urls import (
    normalize_url as weblens_normalize_url,
    strip_tracking as weblens_strip_tracking,
    TRACKING_EXACT,
    TRACKING_PREFIXES,
)
from src.weblens.lexical import query_terms as weblens_query_terms, STOPWORDS as WEBLENS_STOPWORDS
from src.weblens.search.router import clean_query as weblens_clean_query, _authority as weblens_authority, AUTHORITY as WEBLENS_AUTHORITY
from webintel.query_engine import rule_plan as webintel_rule_plan
from webintel.authority import authority_score as webintel_authority_score, authority_label as webintel_authority_label
from webintel.search_pipeline import canonicalize as webintel_canonicalize


def test_tracking_parameter_stripping():
    test_cases = [
        (
            "https://example.com/article?utm_source=twitter&utm_medium=social&utm_campaign=launch&id=42#header",
            "utm_* and fragment",
        ),
        (
            "https://docs.python.org/3/library/asyncio.html?fbclid=IwAR12345&gclid=67890&ref=google",
            "fbclid, gclid, ref",
        ),
        (
            "https://github.com/astral-sh/uv/releases?mc_cid=abc12345&mc_eid=def67890&_ga=GA1.2.12345",
            "mailchimp & google analytics",
        ),
        (
            "https://arstechnica.com/gadgets/2026/01/new-chip/?source=rss&ref_src=twsrc&si=trackid",
            "source, ref_src, si",
        ),
    ]

    results = []
    for raw_url, desc in test_cases:
        e_norm = engine_normalize_url(raw_url)
        p_norm = pipeline_normalize_url(raw_url)
        w_norm = weblens_normalize_url(raw_url)
        w_strip = weblens_strip_tracking(raw_url)
        wi_canon = webintel_canonicalize(raw_url)

        results.append({
            "raw": raw_url,
            "description": desc,
            "engine_aggregator": e_norm,
            "search_pipeline": p_norm,
            "weblens_urls": w_norm,
            "weblens_strip": w_strip,
            "webintel_canonicalize": wi_canon,
        })
    return results


def test_subquery_capping():
    prompts = [
        "What is the difference between git rebase and git merge in team workflows with linear history?",
        "Can you please tell me how to resolve TypeError: unhashable type: 'list' when building dictionary in Python 3.11",
        "Compare uv and pip for Python packaging caching performance and dependency resolution speed",
        "Latest stable release features of Linux kernel 6.12 with LTS roadmap",
        "Simple quick query",
    ]

    results = []
    for p in prompts:
        src_engine_plan = _rule_plan(p)
        root_plan = root_query_engine.build_rule_based_plan(p)
        webintel_plan = webintel_rule_plan(p)

        results.append({
            "prompt": p,
            "src_engine_subqueries_count": len(src_engine_plan.sub_queries),
            "src_engine_subqueries": src_engine_plan.sub_queries,
            "src_engine_intent": src_engine_plan.intent,
            "src_engine_locks": src_engine_plan.lexical_locks,
            "root_subqueries_count": len(root_plan.sub_queries),
            "root_subqueries": root_plan.sub_queries,
            "webintel_subqueries_count": len(webintel_plan.subqueries()),
            "webintel_subqueries": webintel_plan.subqueries(),
        })
    return results


def test_stopwords_and_filler_removal():
    test_queries = [
        "Can you please tell me about Python asyncio event loop",
        "Could you please explain what is the difference between git rebase and git merge",
        "I want to know how to install and configure Docker container on Ubuntu 24.04",
        "Give me information on latest breaking news about OpenAI GPT-5 release date",
    ]

    results = []
    for q in test_queries:
        plan = _rule_plan(q)
        root_clean = root_query_engine.clean_conversational_query(q)
        weblens_clean = weblens_clean_query(q)
        wl_terms, wl_phrases = weblens_query_terms(q)

        results.append({
            "raw_query": q,
            "src_engine_primary": plan.primary_keyword_query,
            "src_engine_bm25_tokens": plan.bm25_tokens,
            "root_clean": root_clean,
            "weblens_clean": weblens_clean,
            "weblens_terms": wl_terms,
        })
    return results


def test_domain_authority_weighting():
    test_domains = [
        # Tier 1 / Primary
        ("https://docs.python.org/3/library/asyncio.html", "Official Python Docs"),
        ("https://developer.mozilla.org/en-US/docs/Web/JavaScript", "MDN Web Docs"),
        ("https://learn.microsoft.com/en-us/azure/", "Microsoft Learn"),
        ("https://github.com/python/cpython", "GitHub Repository"),
        ("https://arxiv.org/abs/1706.03762", "arXiv Research"),
        ("https://www.cdc.gov/flu/weekly/", "US Government (.gov)"),
        ("https://cs.stanford.edu/research", "University (.edu)"),
        ("https://www.cam.ac.uk/research", "UK Academic (.ac.uk)"),
        # Tier 2 / Press
        ("https://www.reuters.com/technology/", "Reuters Technology"),
        ("https://arstechnica.com/gadgets/", "Ars Technica"),
        # Low Quality / Farms / Aggregators
        ("https://www.w3schools.com/python/", "W3Schools"),
        ("https://www.geeksforgeeks.org/python-list/", "GeeksForGeeks"),
        ("https://www.quora.com/What-is-Python", "Quora"),
        ("https://www.pinterest.com/pin/12345", "Pinterest"),
        ("https://best10deals.online/article", "Low quality TLD .online"),
        ("https://supercheapproducts.xyz/download", "Low quality TLD .xyz"),
        ("https://spamtutorial.site/guide", "Low quality TLD .site"),
    ]

    results = []
    for url, label in test_domains:
        e_score = engine_authority_score(url)
        e_tier = engine_authority_tier(url)
        p_auth = pipeline_domain_authority(url)
        w_auth = weblens_authority(url)
        wi_score = webintel_authority_score(url)
        wi_label = webintel_authority_label(url)

        results.append({
            "url": url,
            "category": label,
            "engine_authority_score": e_score,
            "engine_authority_tier": e_tier,
            "pipeline_domain_authority": p_auth,
            "weblens_authority": w_auth,
            "webintel_authority_score": wi_score,
            "webintel_authority_label": wi_label,
        })
    return results


async def evaluate_held_out_queries():
    held_out_queries = [
        {
            "id": "Q1_TECH_BUG",
            "category": "technical_bug",
            "query": "TypeError: unhashable type: 'list' Python dictionary key fix",
            "expected_terms": ["unhashable", "list", "tuple", "dict"],
        },
        {
            "id": "Q2_TECH_DOCS",
            "category": "official_documentation",
            "query": "Python asyncio TaskGroup create_task example usage 3.11",
            "expected_terms": ["taskgroup", "asyncio", "create_task"],
        },
        {
            "id": "Q3_COMPARISON",
            "category": "comparison",
            "query": "PostgreSQL vs MySQL performance differences MVCC concurrency",
            "expected_terms": ["postgresql", "mysql", "mvcc"],
        },
        {
            "id": "Q4_CONVERSATIONAL",
            "category": "conversational_filler",
            "query": "Can you please tell me how to configure FastAPI CORS middleware in Python application",
            "expected_terms": ["fastapi", "cors", "middleware"],
        },
        {
            "id": "Q5_RECENCY_NEWS",
            "category": "news_recency",
            "query": "Linux kernel 6.12 release notes features LTS roadmap",
            "expected_terms": ["linux", "kernel", "6.12"],
        },
        {
            "id": "Q6_LEXICAL_LOCKS",
            "category": "lexical_locks",
            "query": 'Pydantic v2.0 "BaseSettings" model_dump json migration',
            "expected_terms": ["pydantic", "basesettings", "migration"],
        },
        {
            "id": "Q7_SECURITY_CVE",
            "category": "security_cve",
            "query": "CVE-2024-38077 Windows Remote Desktop Licensing service RCE",
            "expected_terms": ["cve-2024-38077", "remote desktop", "rce"],
        },
        {
            "id": "Q8_ACADEMIC_RESEARCH",
            "category": "academic_research",
            "query": "Attention Is All You Need Transformer architecture Vaswani 1706.03762",
            "expected_terms": ["transformer", "attention", "vaswani"],
        },
        {
            "id": "Q9_CLI_ERROR",
            "category": "cli_error",
            "query": "git push --force-with-lease rejected remote contains work that you do not have locally",
            "expected_terms": ["git", "push", "force-with-lease", "rejected"],
        },
        {
            "id": "Q10_HOAX_ZERO_ACCURACY",
            "category": "zero_fake_accuracy_gate",
            "query": "Windows 14 official release date ISO download requirements",
            "expected_terms": ["windows", "14"],
        },
    ]

    aggregator = SearchAggregator()
    results = []

    for item in held_out_queries:
        qid = item["id"]
        q = item["query"]
        expected = item["expected_terms"]

        # 1. Query planning
        plan = _rule_plan(q)

        # 2. Search execution
        t0 = time.perf_counter()
        search_res = await aggregator.search(q, count=5, max_tokens=600)
        lat_s = time.perf_counter() - t0

        # 3. Analyze results
        hit_urls = [r.url for r in search_res.results]
        hit_domains = [get_domain(u) for u in hit_urls]
        unique_domains = list(set(hit_domains))

        # Check domain cap enforcement (max 2 per domain)
        from collections import Counter
        dom_counts = Counter(hit_domains)
        max_per_domain = max(dom_counts.values()) if dom_counts else 0
        domain_cap_respected = max_per_domain <= 2

        # Check token budget compliance
        total_snippet_tokens = sum(len(aggregator.tokenizer.encode(r.snippet)) for r in search_res.results)
        response_blob = json.dumps(search_res.to_dict(), separators=(",", ":"))
        total_response_tokens = len(aggregator.tokenizer.encode(response_blob))

        # Precision / relevance coverage
        relevance_hits = 0
        for r in search_res.results:
            text = (r.title + " " + r.snippet).lower()
            if any(term.lower() in text for term in expected):
                relevance_hits += 1
        precision = relevance_hits / len(search_res.results) if search_res.results else 0.0

        # Domain authority average
        auth_scores = [engine_authority_score(u) for u in hit_urls]
        avg_auth = sum(auth_scores) / len(auth_scores) if auth_scores else 0.0

        results.append({
            "id": qid,
            "category": item["category"],
            "query": q,
            "status": search_res.status,
            "latency_s": round(lat_s, 3),
            "results_count": len(search_res.results),
            "unique_domains_count": len(unique_domains),
            "max_per_domain": max_per_domain,
            "domain_cap_respected": domain_cap_respected,
            "total_snippet_tokens": total_snippet_tokens,
            "total_response_tokens": total_response_tokens,
            "relevance_precision_at_k": round(precision, 3),
            "average_authority_score": round(avg_auth, 3),
            "plan_intent": plan.intent,
            "plan_subqueries": plan.sub_queries,
            "plan_lexical_locks": plan.lexical_locks,
            "hit_urls": hit_urls[:3],
        })

    return results


async def main():
    print("=== RUNNING EMPIRICAL BENCHMARK ===")
    t_start = time.perf_counter()

    print("\n--- 1. Testing Tracking Parameter Stripping ---")
    tracking_res = test_tracking_parameter_stripping()
    print(f"Verified {len(tracking_res)} tracking parameter stripping scenarios.")

    print("\n--- 2. Testing Sub-Query Capping ---")
    subquery_res = test_subquery_capping()
    for item in subquery_res:
        print(f"Query: '{item['prompt'][:50]}...' -> Subqueries: src={item['src_engine_subqueries_count']}, root={item['root_subqueries_count']}, webintel={item['webintel_subqueries_count']}")

    print("\n--- 3. Testing Stopwords & Filler Removal ---")
    stopword_res = test_stopwords_and_filler_removal()
    for item in stopword_res:
        print(f"Raw: '{item['raw_query'][:45]}...' -> Primary: '{item['src_engine_primary'][:45]}...'")

    print("\n--- 4. Testing Domain Authority Weighting ---")
    domain_res = test_domain_authority_weighting()
    for item in domain_res:
        print(f"URL: {item['url'][:40]} | Category: {item['category']} | EngineScore: {item['engine_authority_score']} | PipelineAuth: {item['pipeline_domain_authority']} | WebIntelScore: {item['webintel_authority_score']} ({item['webintel_authority_label']})")

    print("\n--- 5. Evaluating Held-Out Queries on Live Search ---")
    held_out_res = await evaluate_held_out_queries()
    for item in held_out_res:
        print(f"[{item['id']}] Status: {item['status']} | Results: {item['results_count']} | Latency: {item['latency_s']}s | Tokens: {item['total_response_tokens']} | P@K: {item['relevance_precision_at_k']} | Domains: {item['unique_domains_count']} (CapRespected: {item['domain_cap_respected']})")

    total_elapsed = time.perf_counter() - t_start
    print(f"\nBenchmark completed in {total_elapsed:.2f}s.")

    output_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_elapsed_s": round(total_elapsed, 3),
        "tracking_tests": tracking_res,
        "subquery_tests": subquery_res,
        "stopword_tests": stopword_res,
        "domain_authority_tests": domain_res,
        "held_out_queries": held_out_res,
    }

    with open("benchmark_search_relevance_results.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print("Saved results to benchmark_search_relevance_results.json")


if __name__ == "__main__":
    asyncio.run(main())
