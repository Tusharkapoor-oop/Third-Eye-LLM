"""Honest head-to-head benchmark: WebLens retrieval vs Tavily ``/search`` (v11).

Both systems are asked the *same* queries from the same labeled dataset
(``weblens-lab/datasets/eval_benchmark_suite_v10.json``) and are scored by the
identical relevance rule against each query's ``acceptable_sources`` labels.

Design rules (deliberate, to keep the comparison honest):

* **No cherry-picking.** Queries are a fixed prefix of an ordered candidate
  list: ``heldout`` split first, then ``development``, each in dataset order.
  Only items with ``is_unanswerable == false`` and ``web_search_equivalent``
  (and at least one label) are eligible. The exact ids graded are written to
  ``results.json`` so anyone can re-run exactly the same slice.
* **Same primitive.** Both systems answer a plain ranked-URL search call with
  top-k = 5: WebLens ``await service.search(query, max_results=5)`` (the real
  package API; note the kwarg is ``max_results``, not ``k``) and Tavily
  ``POST https://api.tavily.com/search`` with ``max_results=5`` and
  ``search_depth="basic"``.
* **Same scoring code.** ``is_relevant``/``hit_at_k``/``precision_at_k``/
  ``ndcg_at_k``/``mrr`` are pure functions shared by both systems and covered by
  known-answer unit tests in ``test_v11_metrics.py``.
* **Same token counter.** ``weblens.tokens.count_json_tokens`` is applied to both
  payloads, and separately to both *results arrays* (the evidence an agent
  actually receives). The results-array number is the headline because Tavily's
  full payload also carries an LLM answer and image lists that WebLens never
  emits; the full-payload number is reported too, unmodified.
* **Contamination guard.** WebLens ships author-curated "official source" hints
  (``weblens.urls.official_source_urls``) that inject deterministic primary-source
  URLs. ``router.py`` says outright that they must be disabled for an honest
  head-to-head because the dataset labels were written by the same author. They
  are therefore **off by default** here (``use_official_source_hints=False``);
  ``--hints`` re-enables them to show the contaminated number for contrast.
* **No retries.** A per-query error is recorded as a miss with the exception
  type; the run continues. A network-level preflight failure aborts loudly
  (exit 2) instead of producing a table full of silent misses.

Usage
-----
    python weblens-lab/evaluations/run_weblens_vs_tavily_v11.py --limit 40
    python weblens-lab/evaluations/run_weblens_vs_tavily_v11.py --limit 40 --split heldout
    python weblens-lab/evaluations/run_weblens_vs_tavily_v11.py --limit 40 --out reports/x

The Tavily key is read from ``TAVILY_API_KEY`` or the repo ``.env``; it is never
written to any output file.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "weblens-lab" / "datasets" / "eval_benchmark_suite_v10.json"
DEFAULT_OUT = REPO_ROOT / "reports" / "weblens-vs-tavily-v11"
CACHE_DIR = REPO_ROOT / ".tmp-bench-cache"

K = 5
# Two-label public suffixes that appear in this dataset's labels.
_TWO_LEVEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "co.jp",
    "or.jp",
    "ne.jp",
    "go.jp",
    "ac.jp",
    "ed.jp",
    "com.au",
    "net.au",
    "org.au",
    "gov.au",
    "co.nz",
    "com.br",
    "com.cn",
    "com.tr",
    "co.in",
    "co.za",
    "com.mx",
    "com.ar",
}


# --------------------------------------------------------------------------- #
# relevance scoring: pure functions, shared by both systems, unit-tested
# --------------------------------------------------------------------------- #
def registrable_domain(host: str) -> str:
    """Best-effort eTLD+1 for the labels used here (no ``tldextract`` dependency)."""
    host = (host or "").lower().strip(".")
    if not host:
        return ""
    # A leading "www." is never the registrable label; dropping it keeps
    # "www.australia.gov.au" from being mistaken for a three-label domain.
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in _TWO_LEVEL_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def host_of(url: str) -> str:
    """Lower-case host of ``url``; empty string when it cannot be parsed."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def is_relevant(url: str, acceptable_sources: list[str]) -> bool:
    """True when the result's host or registrable domain matches a label.

    A label matches when the host equals it, ends with ``"." + label``, or its
    registrable domain equals/ends with it. That covers both directions used in
    the dataset: label ``wikipedia.org`` vs host ``en.wikipedia.org`` and label
    ``australia.gov.au`` vs host ``www.australia.gov.au``.
    """
    host = host_of(url)
    if not host:
        return False
    domain = registrable_domain(host)
    for raw in acceptable_sources or []:
        label = (raw or "").lower().strip().strip(".")
        if not label:
            continue
        if host == label or host.endswith("." + label):
            return True
        if domain and (domain == label or domain.endswith("." + label)):
            return True
    return False


def hit_at_k(urls: list[str], labels: list[str], k: int = K) -> float:
    """1.0 when at least one of the top-k URLs is relevant."""
    return 1.0 if any(is_relevant(u, labels) for u in urls[:k]) else 0.0


def precision_at_k(urls: list[str], labels: list[str], k: int = K) -> float:
    """Relevant fraction of the top-k URLs (denominator is always k)."""
    if k <= 0:
        return 0.0
    return sum(1 for u in urls[:k] if is_relevant(u, labels)) / k


def _dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(urls: list[str], labels: list[str], k: int = K) -> float:
    """Binary-gain nDCG@k with log2 discounts.

    IDCG assumes an idealized ranking in which all k positions are relevant,
    because the dataset labels are domains, not a judged document set, so the
    true number of relevant documents is unknown and unbounded. Absolute values
    are therefore conservative (a single relevant hit at rank 1 scores ~0.34).
    """
    if k <= 0:
        return 0.0
    gains = [1.0 if is_relevant(u, labels) else 0.0 for u in urls[:k]]
    idcg = _dcg([1.0] * k)
    if idcg <= 0:
        return 0.0
    return _dcg(gains) / idcg


def ndcg_at_k_label_cap(urls: list[str], labels: list[str], k: int = K) -> float:
    """Sensitivity variant: IDCG capped by the number of distinct labels.

    Reported alongside the headline for transparency; not used for the verdict.
    """
    if k <= 0:
        return 0.0
    gains = [1.0 if is_relevant(u, labels) else 0.0 for u in urls[:k]]
    ideal = min(k, max(1, len({(x or "").lower().strip() for x in labels if x})))
    idcg = _dcg([1.0] * ideal)
    if idcg <= 0:
        return 0.0
    return min(1.0, _dcg(gains) / idcg)


def mrr(urls: list[str], labels: list[str], k: int = K) -> float:
    """Reciprocal rank of the first relevant result (0.0 when none in top-k)."""
    for i, url in enumerate(urls[:k], start=1):
        if is_relevant(url, labels):
            return 1.0 / i
    return 0.0


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile (p in 0..100); 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (p / 100.0) * (len(ordered) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))


def bootstrap_ci(values: list[float], iterations: int = 2000, seed: int = 12345) -> tuple[float, float]:
    """95% percentile bootstrap CI for the mean (seeded => deterministic)."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * (iterations - 1))]
    hi = means[int(0.975 * (iterations - 1))]
    return (float(lo), float(hi))


def paired_bootstrap_ci(
    a: list[float], b: list[float], iterations: int = 2000, seed: int = 12345
) -> tuple[float, float]:
    """95% percentile bootstrap CI for the mean paired difference ``a - b``."""
    if not a or len(a) != len(b):
        return (0.0, 0.0)
    return bootstrap_ci([x - y for x, y in zip(a, b, strict=True)], iterations=iterations, seed=seed)


# --------------------------------------------------------------------------- #
# dataset selection and IO
# --------------------------------------------------------------------------- #
def _eligible(item: dict[str, Any]) -> bool:
    return (
        not item.get("is_unanswerable", True)
        and bool(item.get("web_search_equivalent", False))
        and bool(item.get("acceptable_sources"))
    )


def select_queries(limit: int, split: str | None = None) -> list[dict[str, Any]]:
    """Deterministic query slice: heldout first, then development, dataset order."""
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    candidates = [q for q in data if _eligible(q)]
    if split:
        candidates = [q for q in candidates if q.get("split") == split]
    else:
        heldout = [q for q in candidates if q.get("split") == "heldout"]
        development = [q for q in candidates if q.get("split") == "development"]
        rest = [q for q in candidates if q.get("split") not in ("heldout", "development")]
        candidates = heldout + development + rest
    return candidates[: max(1, limit)]


def _load_tavily_key() -> str:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("TAVILY_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    raise SystemExit("TAVILY_API_KEY not found in the environment or in .env")


# --------------------------------------------------------------------------- #
# the two systems
# --------------------------------------------------------------------------- #
@dataclass
class Row:
    """One graded query: both systems' ranked URLs, timings, tokens, errors."""

    id: str
    query: str
    category: str
    split: str
    labels: list[str]
    order: list[str] = field(default_factory=list)
    weblens_urls: list[str] = field(default_factory=list)
    tavily_urls: list[str] = field(default_factory=list)
    weblens_ms: float = 0.0
    tavily_ms: float = 0.0
    weblens_tokens: int = 0
    tavily_tokens: int = 0
    weblens_payload_tokens: int = 0
    tavily_payload_tokens: int = 0
    weblens_status: str = ""
    weblens_providers: list[str] = field(default_factory=list)
    tavily_status: str = ""
    weblens_error: str | None = None
    tavily_error: str | None = None


async def _weblens_search(service, query: str, timeout_s: float) -> dict[str, Any]:
    """One WebLens search call. Returns the service payload (never raises)."""
    from weblens.tokens import count_json_tokens

    payload = await asyncio.wait_for(service.search(query, max_results=K), timeout=timeout_s)
    if not isinstance(payload, dict):  # defensive: API change would be loud, not silent
        raise TypeError(f"WebLens.search returned {type(payload).__name__}, expected dict")
    hits = payload.get("res") or []
    urls = [str(h.get("u") or "") for h in hits if isinstance(h, dict)]
    return {
        "urls": [u for u in urls if u],
        "tokens": count_json_tokens(hits),
        "payload_tokens": count_json_tokens(payload),
        "status": str(payload.get("status") or ""),
        "providers": [str(p) for p in (payload.get("prov") or [])],
        "error": None if payload.get("status") != "error" else str(payload.get("msg") or payload.get("err") or "error"),
    }


async def _tavily_search(client, key: str, query: str, timeout_s: float) -> dict[str, Any]:
    """One Tavily /search call. Returns URL list + tokens (never raises for HTTP)."""
    from weblens.tokens import count_json_tokens

    payload = {
        "api_key": key,
        "query": query,
        "max_results": K,
        "search_depth": "basic",
    }
    resp = await client.post("https://api.tavily.com/search", json=payload, timeout=timeout_s)
    if resp.status_code != 200:
        raise RuntimeError(f"tavily_http_{resp.status_code}: {resp.text[:160]}")
    data = resp.json()
    results = data.get("results") or []
    urls = [str(r.get("url") or "") for r in results if isinstance(r, dict)]
    return {
        "urls": [u for u in urls if u],
        "tokens": count_json_tokens(results),
        "payload_tokens": count_json_tokens(data),
        "status": str(data.get("response_time") and "ok" or "ok"),
        "providers": [],
        "error": None,
    }


async def _grade_one(service, client, key: str, item: dict[str, Any], index: int, timeout_s: float) -> Row:
    """Run both systems on one query and record everything, including failures."""
    row = Row(
        id=str(item["id"]),
        query=str(item["query"]),
        category=str(item.get("category") or ""),
        split=str(item.get("split") or ""),
        labels=[str(x) for x in (item.get("acceptable_sources") or [])],
    )
    # Alternate which system goes first so neither always gets the colder path.
    row.order = ["weblens", "tavily"] if index % 2 == 0 else ["tavily", "weblens"]

    for system in row.order:
        if system == "weblens":
            t0 = time.perf_counter()
            try:
                out = await _weblens_search(service, row.query, timeout_s)
                row.weblens_urls = out["urls"]
                row.weblens_tokens = int(out["tokens"])
                row.weblens_payload_tokens = int(out["payload_tokens"])
                row.weblens_status = out["status"]
                row.weblens_providers = out["providers"]
                row.weblens_error = out["error"]
            except Exception as exc:  # noqa: BLE001 - every failure is recorded, then graded as a miss
                row.weblens_error = f"{type(exc).__name__}: {exc}"[:220]
                row.weblens_status = "exception"
            row.weblens_ms = (time.perf_counter() - t0) * 1000.0
        else:
            t0 = time.perf_counter()
            try:
                out = await _tavily_search(client, key, row.query, timeout_s)
                row.tavily_urls = out["urls"]
                row.tavily_tokens = int(out["tokens"])
                row.tavily_payload_tokens = int(out["payload_tokens"])
                row.tavily_status = out["status"]
            except Exception as exc:  # noqa: BLE001 - recorded as a miss, run continues
                row.tavily_error = f"{type(exc).__name__}: {exc}"[:220]
                row.tavily_status = "exception"
            row.tavily_ms = (time.perf_counter() - t0) * 1000.0

    return row


async def _preflight(service, client, key: str, timeout_s: float) -> None:
    """Fail loudly when either system cannot be reached at all."""
    probe = "python programming language"
    try:
        await _tavily_search(client, key, probe, timeout_s)
    except Exception as exc:  # noqa: BLE001 - preflight is exactly where we must be loud
        raise SystemExit(
            "PREFLIGHT FAILED: Tavily is unreachable or rejected the key "
            f"({type(exc).__name__}: {exc}). Refusing to emit a table of silent misses."
        ) from exc
    try:
        out = await _weblens_search(service, probe, timeout_s * 2)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"PREFLIGHT FAILED: WebLens search raised ({type(exc).__name__}: {exc}). Refusing to continue."
        ) from exc
    if not out["urls"] and out["error"]:
        raise SystemExit(f"PREFLIGHT FAILED: WebLens returned no results and an error ({out['error']}).")


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #
def _aggregate(rows: list[Row], prefix: str) -> dict[str, Any]:
    urls_key = f"{prefix}_urls"
    ms_key = f"{prefix}_ms"
    tok_key = f"{prefix}_tokens"
    ptok_key = f"{prefix}_payload_tokens"
    err_key = f"{prefix}_error"

    hits, prec, ndcg, ndcg_lc, rr, lat, toks, ptoks = [], [], [], [], [], [], [], []
    successes = 0
    for row in rows:
        urls = getattr(row, urls_key)
        err = getattr(row, err_key)
        if err is None and urls:
            successes += 1
        hits.append(hit_at_k(urls, row.labels))
        prec.append(precision_at_k(urls, row.labels))
        ndcg.append(ndcg_at_k(urls, row.labels))
        ndcg_lc.append(ndcg_at_k_label_cap(urls, row.labels))
        rr.append(mrr(urls, row.labels))
        lat.append(float(getattr(row, ms_key)))
        toks.append(float(getattr(row, tok_key)))
        ptoks.append(float(getattr(row, ptok_key)))

    n = len(rows)
    return {
        "n": n,
        "success_rate": successes / n if n else 0.0,
        "hit_at_5": statistics.fmean(hits) if hits else 0.0,
        "p_at_5": statistics.fmean(prec) if prec else 0.0,
        "ndcg_at_5": statistics.fmean(ndcg) if ndcg else 0.0,
        "ndcg_at_5_label_cap": statistics.fmean(ndcg_lc) if ndcg_lc else 0.0,
        "mrr": statistics.fmean(rr) if rr else 0.0,
        "p50_ms": percentile(lat, 50),
        "p95_ms": percentile(lat, 95),
        "mean_ms": statistics.fmean(lat) if lat else 0.0,
        "mean_tokens": statistics.fmean(toks) if toks else 0.0,
        "mean_payload_tokens": statistics.fmean(ptoks) if ptoks else 0.0,
        "errors": sum(1 for row in rows if getattr(row, err_key) is not None),
        "_hits": hits,
        "_prec": prec,
        "_ndcg": ndcg,
        "_mrr": rr,
    }


def _with_ci(stats: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in stats.items() if not k.startswith("_")}
    out["p_at_5_ci95"] = list(bootstrap_ci(stats["_prec"]))
    out["ndcg_at_5_ci95"] = list(bootstrap_ci(stats["_ndcg"]))
    out["mrr_ci95"] = list(bootstrap_ci(stats["_mrr"]))
    return out


def find_anomalies(rows: list[Row]) -> list[dict[str, Any]]:
    """Flag rows a human should look at; nothing is excluded from the metrics."""
    anomalies: list[dict[str, Any]] = []
    both_zero = sum(1 for r in rows if not r.weblens_urls and not r.tavily_urls) or 1
    lat_cut = percentile([r.weblens_ms for r in rows] + [r.tavily_ms for r in rows], 95) * 2
    for row in rows:
        wl_rel = sum(1 for u in row.weblens_urls[:K] if is_relevant(u, row.labels))
        tv_rel = sum(1 for u in row.tavily_urls[:K] if is_relevant(u, row.labels))
        reasons = []
        if row.weblens_error:
            reasons.append(f"weblens_error={row.weblens_error}")
        if row.tavily_error:
            reasons.append(f"tavily_error={row.tavily_error}")
        if row.weblens_status not in ("ok", "partial", ""):
            reasons.append(f"weblens_status={row.weblens_status}")
        if row.weblens_urls and wl_rel == 0 and tv_rel == 0:
            reasons.append("no_relevant_result_from_either")
        if row.weblens_urls and not row.tavily_urls:
            reasons.append("tavily_returned_nothing")
        if row.tavily_urls and not row.weblens_urls:
            reasons.append("weblens_returned_nothing")
        if row.weblens_ms > lat_cut or row.tavily_ms > lat_cut:
            reasons.append("latency_outlier")
        if both_zero and not row.weblens_urls and not row.tavily_urls:
            reasons.append("empty_for_both")
        if reasons:
            anomalies.append(
                {
                    "id": row.id,
                    "query": row.query,
                    "weblens_relevant": wl_rel,
                    "tavily_relevant": tv_rel,
                    "weblens_urls": row.weblens_urls,
                    "tavily_urls": row.tavily_urls,
                    "reasons": reasons,
                }
            )
    return anomalies


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
async def run(
    limit: int,
    split: str | None,
    sleep_s: float,
    concurrency: int,
    timeout_s: float,
    hints: bool = False,
) -> dict[str, Any]:
    import httpx

    from weblens.config import Settings
    from weblens.service import WebLens

    key = _load_tavily_key()
    queries = select_queries(limit, split)
    if not queries:
        raise SystemExit("no eligible queries selected from the dataset")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Provider list follows the *product* default unless an ablation override is
    # explicitly requested, so the benchmark always measures what ships.
    overrides: dict[str, Any] = {}
    provider_override = os.environ.get("WEBLENS_SEARCH_PROVIDERS", "").strip()
    if provider_override:
        overrides["search_providers"] = provider_override
    settings = Settings(
        cache_dir=CACHE_DIR,
        cache_enabled=False,
        allow_browser=False,
        tavily_api_key=None,  # WebLens must NOT use the system under test (Tavily) as a provider
        total_timeout_s=max(30.0, timeout_s),
        **overrides,
    )
    # The curated hints alias the dataset's own label vocabulary, so leaving them
    # on measures label leakage rather than retrieval quality. Off unless asked.
    if hasattr(settings, "use_official_source_hints"):
        settings.use_official_source_hints = bool(hints)
    else:  # older settings model: attribute absent, nothing to disable
        hints = False
    service = WebLens(settings)
    rows: list[Row] = []
    started = time.time()
    progress = {"done": 0, "total": len(queries)}

    async def worker(sem: asyncio.Semaphore, index: int, item: dict[str, Any], client) -> Row:
        async with sem:
            row = await _grade_one(service, client, key, item, index, timeout_s)
        progress["done"] += 1
        print(
            f"[{progress['done']}/{progress['total']}] {row.id} "
            f"wl={len(row.weblens_urls)}u/{row.weblens_ms:.0f}ms"
            f"{'/ERR' if row.weblens_error else ''} "
            f"tv={len(row.tavily_urls)}u/{row.tavily_ms:.0f}ms"
            f"{'/ERR' if row.tavily_error else ''}",
            flush=True,
        )
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)
        return row

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await _preflight(service, client, key, min(timeout_s, 30.0))
            print("preflight ok (both systems reachable)\n", flush=True)
            sem = asyncio.Semaphore(max(1, concurrency))
            rows = list(
                await asyncio.gather(
                    *(worker(sem, i, item, client) for i, item in enumerate(queries)),
                )
            )
    finally:
        await service.close()

    rows.sort(key=lambda r: [q["id"] for q in queries].index(r.id))  # dataset order in output

    wl_raw = _aggregate(rows, "weblens")
    tv_raw = _aggregate(rows, "tavily")
    paired_prec = [a - b for a, b in zip(wl_raw["_prec"], tv_raw["_prec"], strict=True)]
    paired_ndcg = [a - b for a, b in zip(wl_raw["_ndcg"], tv_raw["_ndcg"], strict=True)]
    wins = sum(1 for d in paired_prec if d > 1e-9)
    losses = sum(1 for d in paired_prec if d < -1e-9)
    ties = len(paired_prec) - wins - losses

    wl = _with_ci(wl_raw)
    tv = _with_ci(tv_raw)
    anomalies = find_anomalies(rows)
    tavily_fail_rate = tv["errors"] / tv["n"] if tv["n"] else 0.0

    summary: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "benchmark": "weblens-vs-tavily-v11",
        "dataset": str(DATASET.relative_to(REPO_ROOT)),
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "k": K,
        "limit": len(rows),
        "limit_requested": limit,
        "split_filter": split,
        "selection_rule": "eligible (is_unanswerable=false, web_search_equivalent=true, >=1 label); "
        "heldout first then development, dataset order; fixed prefix of --limit",
        "query_ids": [r.id for r in rows],
        "config": {
            "weblens_api": f"weblens.service.WebLens.search(query, max_results={K})",
            "weblens_providers": settings.search_providers,
            "weblens_search_mode": settings.search_mode,
            "weblens_cache_enabled": False,
            "weblens_use_official_source_hints": bool(settings.use_official_source_hints),
            "weblens_tavily_provider_disabled": True,
            "weblens_official_source_hints": bool(hints),
            "tavily": {"search_depth": "basic", "max_results": K},
            "per_query_timeout_s": timeout_s,
            "retries": 0,
            "concurrency": max(1, concurrency),
            "sleep_between_queries_s": sleep_s,
            "tokens_headline": "count_json_tokens(results array) for both systems",
            "tokens_secondary": "count_json_tokens(full response payload) for both systems",
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pytest_not_used": True,
        },
        "wall_clock_s": round(time.time() - started, 1),
        "data_quality": {
            "tavily_error_rate": round(tavily_fail_rate, 3),
            "weblens_error_rate": round(wl["errors"] / wl["n"], 3) if wl["n"] else 0.0,
            "loud_warning": (
                "tavily error rate > 10%: treat this run as INVALID and re-run" if tavily_fail_rate > 0.10 else None
            ),
        },
        "weblens": wl,
        "tavily": tv,
        "paired": {
            "p_at_5_diff": statistics.fmean(paired_prec),
            "p_at_5_diff_ci95": list(paired_bootstrap_ci(wl_raw["_prec"], tv_raw["_prec"])),
            "ndcg_at_5_diff": statistics.fmean(paired_ndcg),
            "ndcg_at_5_diff_ci95": list(paired_bootstrap_ci(wl_raw["_ndcg"], tv_raw["_ndcg"])),
            "wins": wins,
            "ties": ties,
            "losses": losses,
        },
        "anomalies": anomalies,
        "rows": [asdict(r) for r in rows],
    }
    return summary


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _verdict(wl: dict[str, Any], tv: dict[str, Any], paired: dict[str, Any], n: int) -> list[str]:
    """Plain-language reading of the measured numbers, including where WebLens loses."""
    out: list[str] = []
    d = paired["p_at_5_diff"]
    lo, hi = paired["p_at_5_diff_ci95"]
    if lo > 0:
        out.append(f"P@5: WebLens ahead by {d:+.3f} (95% CI {lo:+.3f}..{hi:+.3f}, excludes zero).")
    elif hi < 0:
        out.append(f"P@5: **WebLens behind** by {d:+.3f} (95% CI {lo:+.3f}..{hi:+.3f}, excludes zero).")
    else:
        out.append(f"P@5: no distinguishable difference ({d:+.3f}, 95% CI {lo:+.3f}..{hi:+.3f} includes zero).")
    dl = paired["ndcg_at_5_diff"]
    nlo, nhi = paired["ndcg_at_5_diff_ci95"]
    out.append(f"nDCG@5: paired difference {dl:+.3f} (95% CI {nlo:+.3f}..{nhi:+.3f}).")
    out.append(f"Per-query P@5 wins/ties/losses: {paired['wins']}/{paired['ties']}/{paired['losses']} over n={n}.")
    if wl["p50_ms"] < tv["p50_ms"]:
        out.append(f"Latency: WebLens faster at p50 ({wl['p50_ms']:.0f}ms vs {tv['p50_ms']:.0f}ms).")
    else:
        out.append(f"Latency: **WebLens slower** at p50 ({wl['p50_ms']:.0f}ms vs {tv['p50_ms']:.0f}ms).")
    if wl["p95_ms"] > tv["p95_ms"]:
        out.append(f"Tail latency: **WebLens slower at p95** ({wl['p95_ms']:.0f}ms vs {tv['p95_ms']:.0f}ms).")
    else:
        out.append(f"Tail latency: WebLens faster at p95 ({wl['p95_ms']:.0f}ms vs {tv['p95_ms']:.0f}ms).")
    if wl["mean_tokens"] < tv["mean_tokens"]:
        out.append(
            f"Result tokens: WebLens returns fewer ({wl['mean_tokens']:.0f} vs {tv['mean_tokens']:.0f} per query)."
        )
    else:
        out.append(
            f"Result tokens: **WebLens returns more** ({wl['mean_tokens']:.0f} vs {tv['mean_tokens']:.0f} per query)."
        )
    if wl["success_rate"] < tv["success_rate"]:
        out.append(
            f"Reliability: **WebLens succeeds less often** ({wl['success_rate']:.1%} vs {tv['success_rate']:.1%})."
        )
    else:
        out.append(f"Reliability: WebLens success {wl['success_rate']:.1%} vs Tavily {tv['success_rate']:.1%}.")
    return out


def write_report(summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    wl, tv, paired = summary["weblens"], summary["tavily"], summary["paired"]

    def f(x: float, nd: int = 3) -> str:
        return f"{x:.{nd}f}"

    lines = [
        "# WebLens vs Tavily — measured head-to-head (v11)",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Dataset: `{summary['dataset']}` (sha256 `{summary['dataset_sha256'][:16]}…`)",
        f"- Queries graded: **{wl['n']}** (fixed prefix; exact ids in `results.json`)",
        f"- Selection: {summary['selection_rule']}",
        f"- k = {summary['k']}; Tavily `search_depth={summary['config']['tavily']['search_depth']}`, "
        f"`max_results={summary['config']['tavily']['max_results']}`",
        f"- WebLens: `WebLens.search(query, max_results={summary['k']})`, providers "
        f"`{summary['config']['weblens_providers']}`, mode `{summary['config']['weblens_search_mode']}`, "
        "cache disabled, Tavily provider disabled",
        f"- Per-query timeout {summary['config']['per_query_timeout_s']:.0f}s, no retries, "
        f"concurrency {summary['config']['concurrency']}, sleep {summary['config']['sleep_between_queries_s']}s",
        f"- Wall clock: {summary['wall_clock_s']}s",
        "",
        "## Results",
        "",
        "| Metric | WebLens | Tavily | Better |",
        "|---|---:|---:|---|",
    ]

    def row(label: str, a: float, b: float, higher_better: bool = True, nd: int = 3) -> None:
        if abs(a - b) < 1e-9:
            better = "tie"
        elif (a > b) == higher_better:
            better = "WebLens"
        else:
            better = "Tavily"
        lines.append(f"| {label} | {f(a, nd)} | {f(b, nd)} | {better} |")

    row("Hit@5", wl["hit_at_5"], tv["hit_at_5"])
    row("P@5", wl["p_at_5"], tv["p_at_5"])
    row("nDCG@5", wl["ndcg_at_5"], tv["ndcg_at_5"])
    row("nDCG@5 (label-capped IDCG, sensitivity)", wl["ndcg_at_5_label_cap"], tv["ndcg_at_5_label_cap"])
    row("MRR", wl["mrr"], tv["mrr"])
    row("Success rate", wl["success_rate"], tv["success_rate"])
    row("p50 latency (ms)", wl["p50_ms"], tv["p50_ms"], higher_better=False, nd=1)
    row("p95 latency (ms)", wl["p95_ms"], tv["p95_ms"], higher_better=False, nd=1)
    row("Mean result tokens", wl["mean_tokens"], tv["mean_tokens"], higher_better=False, nd=1)
    row("Mean full-payload tokens", wl["mean_payload_tokens"], tv["mean_payload_tokens"], higher_better=False, nd=1)

    lines += [
        "",
        "## 95% bootstrap CIs (2000 resamples, seeded)",
        "",
        "| Metric | WebLens mean [CI] | Tavily mean [CI] |",
        "|---|---|---|",
        f"| P@5 | {f(wl['p_at_5'])} [{f(wl['p_at_5_ci95'][0])}, {f(wl['p_at_5_ci95'][1])}] "
        f"| {f(tv['p_at_5'])} [{f(tv['p_at_5_ci95'][0])}, {f(tv['p_at_5_ci95'][1])}] |",
        f"| nDCG@5 | {f(wl['ndcg_at_5'])} [{f(wl['ndcg_at_5_ci95'][0])}, {f(wl['ndcg_at_5_ci95'][1])}] "
        f"| {f(tv['ndcg_at_5'])} [{f(tv['ndcg_at_5_ci95'][0])}, {f(tv['ndcg_at_5_ci95'][1])}] |",
        f"| MRR | {f(wl['mrr'])} [{f(wl['mrr_ci95'][0])}, {f(wl['mrr_ci95'][1])}] "
        f"| {f(tv['mrr'])} [{f(tv['mrr_ci95'][0])}, {f(tv['mrr_ci95'][1])}] |",
        "",
        "## Paired comparison (same queries)",
        "",
        f"- P@5 difference (WebLens − Tavily): **{paired['p_at_5_diff']:+.3f}** "
        f"[{paired['p_at_5_diff_ci95'][0]:+.3f}, {paired['p_at_5_diff_ci95'][1]:+.3f}]",
        f"- nDCG@5 difference: **{paired['ndcg_at_5_diff']:+.3f}** "
        f"[{paired['ndcg_at_5_diff_ci95'][0]:+.3f}, {paired['ndcg_at_5_diff_ci95'][1]:+.3f}]",
        f"- Win / tie / loss (P@5): **{paired['wins']} / {paired['ties']} / {paired['losses']}**",
        "",
        "## Honest reading",
        "",
    ]
    lines += [f"- {line}" for line in _verdict(wl, tv, paired, wl["n"])]

    lines += [
        "",
        "## Where WebLens loses (explicit)",
        "",
    ]
    losses = [s for s in _verdict(wl, tv, paired, wl["n"]) if "behind" in s or "slower" in s or "more" in s]
    if losses:
        lines += [f"- {s.replace('**', '')}" for s in losses]
    else:
        lines.append("- In this sample no aggregate metric favours Tavily; per-query losses still exist (see rows).")
    if paired["losses"]:
        worst = sorted(
            summary["rows"],
            key=lambda r: (
                precision_at_k(r["tavily_urls"], r["labels"]) - precision_at_k(r["weblens_urls"], r["labels"])
            ),
            reverse=True,
        )[:5]
        lines += ["", "Largest per-query P@5 losses (Tavily better):", ""]
        for r in worst:
            wlp = precision_at_k(r["weblens_urls"], r["labels"])
            tvp = precision_at_k(r["tavily_urls"], r["labels"])
            if tvp > wlp:
                lines.append(f"- `{r['id']}`: WebLens P@5={wlp:.1f} vs Tavily P@5={tvp:.1f} — {r['query'][:110]}")

    lines += ["", "## Anomalies flagged for human review", ""]
    if summary["anomalies"]:
        for a in summary["anomalies"][:25]:
            lines.append(f"- `{a['id']}` — {', '.join(a['reasons'])}")
        if len(summary["anomalies"]) > 25:
            lines.append(f"- … and {len(summary['anomalies']) - 25} more in `results.json` (`anomalies`)")
    else:
        lines.append("- None.")

    lines += [
        "",
        "## What the labels actually measure (read this before quoting anything)",
        "",
        "Both systems are scored only on whether their ranked URLs land on the dataset's",
        "`acceptable_sources` domains. That rewards *authoritative sources*, not *correct answers*:",
        "a page on the right domain can still be off-topic, and a perfect answer on an unlabelled",
        "domain scores zero. Read this as an authority / source-selection signal, not a truth benchmark.",
        "",
        "## Contamination control (why the curated hints are off)",
        "",
        "WebLens ships an author-curated `official_source_urls()` hint list that injects deterministic",
        "primary-source URLs for well-known topics. Its own `router.py` comment says these must be",
        "disabled for an honest head-to-head, because the hint list and the dataset labels share an",
        "author.",
        "",
        "**This report only ever states the configuration it was produced with.** To quantify the",
        "hint effect or run-to-run stability, run the script twice with `--hints` on/off and compare",
        "the two `results.json` files — the numbers are intentionally *not* baked into the template,",
        "because hardcoded tables cannot be audited against the artifacts they claim to summarise.",
        "",
        "Measured effect when both runs are done on the same provider chain (from this project's",
        "v11 comparison, `reports/weblens-vs-tavily-v11/README.md`):",
        "",
        "| Run | WebLens P@5 | WebLens nDCG@5 | WebLens MRR | WebLens Hit@5 |",
        "|---|---:|---:|---:|---:|",
        f"| hints OFF (this report's setting) | {wl['p_at_5']:.3f} | {wl['ndcg_at_5']:.3f} | "
        f"{wl['mrr']:.3f} | {wl['hit_at_5']:.3f} |",
        "| hints ON (label-contaminated, separate run) | see that run's own results.json | — | — | — |",
        "",
        "The curated hints are known to inflate WebLens P@5 substantially on these queries. Any",
        "WebLens-vs-Tavily figure produced with hints enabled is measuring label leakage, not",
        "retrieval quality.",
        "",
        "## Run-to-run stability",
        "",
        "Not asserted here. Keyless HTML providers (mwmbl/bing/yahoo) return partly different result",
        "sets per call, so quality metrics wobble between runs; Tavily itself was observed to vary",
        "between runs too (its P@5 and p50 changed between the two v11 runs). Treat a single run as",
        "indicative and re-run to confirm any close call. The 95% CIs above are the intended",
        "uncertainty estimate.",
        "",
        "## Caveats (read before quoting any number)",
        "",
        "- **Labels are domains, not judged documents.** Link relevance is domain matching against "
        "`acceptable_sources`; it rewards authoritative sources but does not prove a snippet answers the query.",
        "- **nDCG IDCG convention:** IDCG assumes all k positions could be relevant (the judged-set size is "
        "unknown), so absolute nDCG values are conservative. A label-capped sensitivity column is reported.",
        "- **Token comparison is not symmetric by nature.** Headline tokens count only the results array; "
        "Tavily's full payload (answer/images/request_id) is reported separately, not compared.",
        "- **One run, one machine, one network path.** Latency is indicative only; no caching on either side "
        "(WebLens `cache_enabled=false`; Tavily has no client cache).",
        "- **WebLens used keyless providers only** (`{p}`) with the Tavily provider explicitly disabled, so this is "
        "WebLens-independent vs Tavily-hosted.".format(p=summary["config"]["weblens_providers"]),
        "- **Contamination guard:** WebLens's author-curated `official_source_urls` hints are "
        f"{'ENABLED (this run is label-contaminated — do not quote it as retrieval quality)' if summary['config']['weblens_official_source_hints'] else 'disabled'}. "
        "`router.py` itself states they must be off for an honest head-to-head, because the dataset labels and "
        "the hint list were written by the same author. With hints on, WebLens scores far higher because it "
        "injects the very domains the labels reward.",
        "- **Paid vs free:** Tavily is a metered hosted API; WebLens here is keyless scraping/aggregation.",
        "",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="WebLens vs Tavily measured head-to-head (v11)")
    ap.add_argument("--limit", type=int, default=40, help="number of graded queries (default 40)")
    ap.add_argument("--split", default=None, choices=[None, "heldout", "development"], help="restrict to one split")
    ap.add_argument("--sleep", type=float, default=0.5, help="politeness sleep between queries (default 0.5s)")
    ap.add_argument("--concurrency", type=int, default=2, help="max concurrent queries (default 2, keep small)")
    ap.add_argument("--timeout", type=float, default=30.0, help="per-query timeout seconds (default 30)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    ap.add_argument(
        "--hints",
        action="store_true",
        help="ENABLE WebLens author-curated official-source hints (label-leaking; off by default)",
    )
    args = ap.parse_args(argv)

    summary = asyncio.run(
        run(
            limit=args.limit,
            split=args.split,
            sleep_s=args.sleep,
            concurrency=args.concurrency,
            timeout_s=args.timeout,
            hints=args.hints,
        )
    )
    write_report(summary, Path(args.out))

    wl, tv, paired = summary["weblens"], summary["tavily"], summary["paired"]
    print(
        f"\nWebLens P@5={wl['p_at_5']:.3f} nDCG@5={wl['ndcg_at_5']:.3f} MRR={wl['mrr']:.3f} "
        f"p50={wl['p50_ms']:.0f}ms tok={wl['mean_tokens']:.0f}\n"
        f"Tavily  P@5={tv['p_at_5']:.3f} nDCG@5={tv['ndcg_at_5']:.3f} MRR={tv['mrr']:.3f} "
        f"p50={tv['p50_ms']:.0f}ms tok={tv['mean_tokens']:.0f}\n"
        f"paired P@5 diff={paired['p_at_5_diff']:+.3f} "
        f"[{paired['p_at_5_diff_ci95'][0]:+.3f}, {paired['p_at_5_diff_ci95'][1]:+.3f}] "
        f"W/T/L={paired['wins']}/{paired['ties']}/{paired['losses']}"
    )
    if summary["data_quality"]["loud_warning"]:
        print(f"\n!! {summary['data_quality']['loud_warning']}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
