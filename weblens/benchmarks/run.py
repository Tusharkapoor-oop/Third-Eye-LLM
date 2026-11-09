# ruff: noqa: ASYNC240
"""Reproducible WebLens benchmark and hard gates.

Run from the repository root:

    uv run python -m benchmarks.run --out benchmarks/results/latest.json

The dataset is committed; the run file stores every payload needed to recompute
the metrics. Nothing here estimates accuracy: unmeasured values stay null.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from weblens.config import Settings
from weblens.mcp_server import build_server
from weblens.service import WebLens
from weblens.tokens import TOKENIZER_NAME, count_json_tokens, count_tokens
from weblens.urls import registrable_domain

FORBIDDEN_FIELDS = {"confidence", "score", "relevance", "probability", "certainty"}
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def load_dataset(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("dataset ids must be unique")
    return rows


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
    return ordered[k]


def is_relevant(url: str, entry: dict[str, Any]) -> bool:
    for prefix in entry.get("relevant_url_prefixes") or []:
        if url.startswith(prefix):
            return True
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    domain = registrable_domain(host)
    for want in entry.get("relevant_domains") or []:
        want = want.lower()
        if host == want or host.endswith("." + want) or domain == want:
            return True
    return False


def citation_errors(items: list[dict[str, Any]], text_key: str) -> list[str]:
    errors: list[str] = []
    for i, item in enumerate(items):
        text = item.get(text_key)
        span = item.get("s")
        url = item.get("u")
        at = item.get("at")
        if not isinstance(text, str) or not text:
            errors.append(f"item {i}: missing text")
            continue
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            errors.append(f"item {i}: bad url")
        if not isinstance(at, str) or not ISO_RE.match(at):
            errors.append(f"item {i}: bad fetched_at {at!r}")
        if (
            not isinstance(span, list)
            or len(span) != 2
            or not all(isinstance(x, int) for x in span)
            or span[0] < 0
            or span[1] < span[0]
        ):
            errors.append(f"item {i}: bad span")
            continue
        if len(text) != span[1] - span[0]:
            errors.append(f"item {i}: text length {len(text)} != span {span}")
    return errors


def forbidden_fields(obj: Any, found: list[str], path: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else key
            if key.lower() in FORBIDDEN_FIELDS:
                found.append(here)
            forbidden_fields(value, found, here)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            forbidden_fields(value, found, f"{path}[{i}]")


def token_budget_ok(payload: dict[str, Any], budget: int) -> tuple[bool, int]:
    actual = count_json_tokens(payload)
    return actual <= budget, actual


def support_for(entry: dict[str, Any], text: str) -> bool | None:
    terms = [t.lower() for t in entry.get("answer_terms") or []]
    if not terms:
        return None
    low = text.lower()
    if entry.get("support_mode") == "all":
        return all(t in low for t in terms)
    return any(t in low for t in terms)


async def run_query(service: WebLens, entry: dict[str, Any], *, extract_limit: int, index: int) -> dict[str, Any]:
    record: dict[str, Any] = {"id": entry["id"], "category": entry["category"], "query": entry["query"]}
    record["expect_conflict"] = bool(entry.get("expect_conflict"))
    t0 = time.perf_counter()
    try:
        search = await service.search(entry["query"], max_results=5, max_tokens=600)
    except Exception as e:  # noqa: BLE001 - harness must keep going
        search = {"status": "harness_error", "err": type(e).__name__, "msg": str(e)[:300]}
    record["search_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    record["search"] = search
    results = search.get("res") or []
    record["search_relevant"] = sum(1 for r in results if is_relevant(r.get("u", ""), entry))
    record["search_returned"] = len(results)
    record["search_precision_at_n"] = record["search_relevant"] / len(results) if results else 0.0
    record["top3_relevant"] = any(is_relevant(r.get("u", ""), entry) for r in results[:3])

    t0 = time.perf_counter()
    try:
        research = await service.deep_research(entry["query"], max_tokens=900)
    except Exception as e:  # noqa: BLE001
        research = {"status": "harness_error", "err": type(e).__name__, "msg": str(e)[:300]}
    record["research_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    record["research"] = research
    findings = research.get("f") or []
    record["research_status_match"] = research.get("status") in entry.get("expect_research_status", [])
    record["research_support"] = support_for(entry, "\n".join(str(f.get("c", "")) for f in findings))
    record["conflict_flagged"] = bool(research.get("conflicts")) or research.get("status") == "conflicting_sources"

    record["extract"] = None
    if index < extract_limit and entry["category"] == "docs" and results:
        url = results[0].get("u")
        if url:
            t0 = time.perf_counter()
            try:
                extract = await service.extract(url, query=entry["query"], max_tokens=1200)
            except Exception as e:  # noqa: BLE001
                extract = {"status": "harness_error", "err": type(e).__name__, "msg": str(e)[:300]}
            record["extract_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            record["extract"] = extract
            record["extract_support"] = support_for(
                entry, "\n".join(str(p.get("x", "")) for p in (extract.get("ps") or []))
            )
    return record


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [r for r in rows if r["category"] in {"docs", "niche_technical", "current_facts"}]
    gated_support = [
        r for r in rows if r["category"] in {"docs", "niche_technical"} and r["research_support"] is not None
    ]
    precision_rows = [r for r in answerable if r["search_returned"] > 0]
    noresult = [r for r in rows if r["category"] == "unanswerable"]
    conflict = [r for r in rows if r.get("expect_conflict")]

    def ratio(num: int, den: int) -> float | None:
        return round(num / den, 4) if den else None

    search_ms = [r["search_ms"] for r in rows if r["search_ms"] is not None]
    research_ms = [r["research_ms"] for r in rows if r["research_ms"] is not None]
    extract_ms = [r["extract_ms"] for r in rows if r.get("extract_ms") is not None]
    return {
        "queries": len(rows),
        "answerable": len(answerable),
        "search_returned": sum(r["search_returned"] for r in answerable),
        "search_relevant": sum(r["search_relevant"] for r in answerable),
        "top3_total": len(answerable),
        "top3_authoritative": sum(1 for r in answerable if r["top3_relevant"]),
        "top3_rate": ratio(sum(1 for r in answerable if r["top3_relevant"]), len(answerable)),
        "precision_at_n": ratio(
            sum(r["search_relevant"] for r in precision_rows),
            sum(r["search_returned"] for r in precision_rows),
        ),
        "support_total": len(gated_support),
        "support_ok": sum(1 for r in gated_support if r["research_support"]),
        "answer_support": ratio(sum(1 for r in gated_support if r["research_support"]), len(gated_support)),
        "status_matches": ratio(sum(1 for r in rows if r["research_status_match"]), len(rows)),
        "noresult_total": len(noresult),
        "noresult_correct": sum(1 for r in noresult if r["research"].get("status") == "no_reliable_result"),
        "noresult_accuracy": ratio(
            sum(1 for r in noresult if r["research"].get("status") == "no_reliable_result"), len(noresult)
        ),
        "conflict_total": len(conflict),
        "conflict_flagged": sum(1 for r in conflict if r["conflict_flagged"]),
        "conflict_recall": ratio(sum(1 for r in conflict if r["conflict_flagged"]), len(conflict)),
        "extract_total": len(extract_ms),
        "extract_support_ok": sum(1 for r in rows if r.get("extract_support")),
        "latency": {
            "search_p50_ms": percentile(search_ms, 50),
            "search_p95_ms": percentile(search_ms, 95),
            "research_p50_ms": percentile(research_ms, 50),
            "research_p95_ms": percentile(research_ms, 95),
            "extract_p50_ms": percentile(extract_ms, 50),
            "extract_p95_ms": percentile(extract_ms, 95),
        },
    }


def evaluate_gates(
    summary: dict[str, Any],
    schema_tokens: int,
    token_violations: int,
    citation_failures: int,
    false_confidence: int,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    lat = summary["latency"]
    gates = [
        ("schema_tokens", schema_tokens <= args.max_schema_tokens, schema_tokens, args.max_schema_tokens),
        ("token_budget_violations", token_violations == 0, token_violations, 0),
        ("citation_failures", citation_failures == 0, citation_failures, 0),
        ("uncalibrated_fields", false_confidence == 0, false_confidence, 0),
        (
            "precision_at_n",
            (summary["precision_at_n"] or 0) >= args.min_precision,
            summary["precision_at_n"],
            args.min_precision,
        ),
        (
            "top3_authoritative",
            (summary["top3_rate"] or 0) >= args.min_top3,
            summary["top3_rate"],
            args.min_top3,
        ),
        (
            "answer_support",
            (summary["answer_support"] or 0) >= args.min_support,
            summary["answer_support"],
            args.min_support,
        ),
        (
            "search_p50_ms",
            (lat["search_p50_ms"] or 1e9) <= args.max_search_p50,
            lat["search_p50_ms"],
            args.max_search_p50,
        ),
        (
            "search_p95_ms",
            (lat["search_p95_ms"] or 1e9) <= args.max_search_p95,
            lat["search_p95_ms"],
            args.max_search_p95,
        ),
        (
            "research_p95_ms",
            (lat["research_p95_ms"] or 1e9) <= args.max_research_p95,
            lat["research_p95_ms"],
            args.max_research_p95,
        ),
    ]
    if summary["noresult_total"]:
        gates.append(
            (
                "noresult_accuracy",
                (summary["noresult_accuracy"] or 0) >= args.min_noresult,
                summary["noresult_accuracy"],
                args.min_noresult,
            )
        )
    if summary["extract_total"] >= 5:
        gates.extend(
            [
                (
                    "extract_p50_ms",
                    (lat["extract_p50_ms"] or 1e9) <= args.max_extract_p50,
                    lat["extract_p50_ms"],
                    args.max_extract_p50,
                ),
                (
                    "extract_p95_ms",
                    (lat["extract_p95_ms"] or 1e9) <= args.max_extract_p95,
                    lat["extract_p95_ms"],
                    args.max_extract_p95,
                ),
            ]
        )
    return [
        {"name": name, "ok": bool(ok), "value": value, "threshold": threshold} for name, ok, value, threshold in gates
    ]


def markdown_report(result: dict[str, Any]) -> str:
    s = result["summary"]
    lat = s["latency"]
    lines = [
        "# WebLens benchmark",
        "",
        f"- started: {result['started_at']}",
        f"- dataset: `{result['dataset']}` ({s['queries']} queries)",
        f"- tokenizer: `{result['tokenizer']}`",
        f"- passed: **{result['passed']}**",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| search precision@n (answerable) | {s['precision_at_n']} ({s['search_relevant']}/{s['search_returned']}) |",
        f"| top-3 authoritative | {s['top3_rate']} ({s['top3_authoritative']}/{s['top3_total']}) |",
        f"| research answer support | {s['answer_support']} ({s['support_ok']}/{s['support_total']}) |",
        f"| status match | {s['status_matches']} |",
        f"| no-result accuracy | {s['noresult_accuracy']} ({s['noresult_correct']}/{s['noresult_total']}) |",
        f"| conflict recall | {s['conflict_recall']} ({s['conflict_flagged']}/{s['conflict_total']}) |",
        f"| search p50 / p95 | {lat['search_p50_ms']} / {lat['search_p95_ms']} ms |",
        f"| extract p50 / p95 | {lat['extract_p50_ms']} / {lat['extract_p95_ms']} ms |",
        f"| research p50 / p95 | {lat['research_p50_ms']} / {lat['research_p95_ms']} ms |",
        f"| schema tokens | {result['schema']['total_tokens']} |",
        "",
        "## Gates",
        "",
        "| gate | ok | value | threshold |",
        "| --- | --- | --- | --- |",
    ]
    for gate in result["gates"]:
        lines.append(f"| {gate['name']} | {gate['ok']} | {gate['value']} | {gate['threshold']} |")
    return "\n".join(lines) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    dataset = load_dataset(Path(args.dataset))
    if args.categories:
        wanted_cats = {c.strip() for c in args.categories.split(",") if c.strip()}
        dataset = [e for e in dataset if e["category"] in wanted_cats]
        if not dataset:
            raise SystemExit(f"no queries matched categories {sorted(wanted_cats)}")
    if args.ids:
        wanted_ids = {x.strip() for x in args.ids.split(",") if x.strip()}
        dataset = [e for e in dataset if e["id"] in wanted_ids]
        missing = wanted_ids - {e["id"] for e in dataset}
        if missing:
            raise SystemExit(f"unknown ids: {sorted(missing)}")
    if args.limit:
        dataset = dataset[: args.limit]
    cache_dir = Path(args.cache_dir)
    if args.fresh_cache and cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(cache_dir=cache_dir, cache_enabled=True, log_level="WARNING")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    started_at = datetime.now(UTC).isoformat()
    t0 = time.perf_counter()
    service = WebLens(settings)
    init_ms = round((time.perf_counter() - t0) * 1000, 1)
    server = build_server(service)
    tools = await server.list_tools()
    dumped = [t.model_dump(by_alias=True, exclude_none=True) for t in tools]
    schema_text = json.dumps(dumped, separators=(",", ":"), ensure_ascii=False)
    schema = {
        "total_tokens": count_tokens(schema_text),
        "per_tool": {
            t.name: count_tokens(json.dumps(d, separators=(",", ":"), ensure_ascii=False))
            for t, d in zip(tools, dumped, strict=True)
        },
    }

    rows: list[dict[str, Any]] = []
    token_violations = 0
    citation_failures = 0
    false_confidence: list[str] = []
    try:
        for index, entry in enumerate(dataset):
            print(f"[{index + 1}/{len(dataset)}] {entry['id']} ...", file=sys.stderr, flush=True)
            row = await run_query(service, entry, extract_limit=args.extract_limit, index=index)
            for key, budget in (("search", 600), ("research", 900), ("extract", 1200)):
                payload = row.get(key)
                if isinstance(payload, dict) and payload.get("status") not in {"harness_error", None}:
                    ok, actual = token_budget_ok(payload, budget)
                    row[f"{key}_actual_tokens"] = actual
                    if not ok:
                        token_violations += 1
            findings = (row.get("research") or {}).get("f") or []
            ps = (row.get("extract") or {}).get("ps") or []
            citation_failures += len(citation_errors(findings, "c"))
            citation_failures += len(citation_errors(ps, "x"))
            forbidden_fields(row.get("search"), false_confidence, f"{entry['id']}.search")
            forbidden_fields(row.get("research"), false_confidence, f"{entry['id']}.research")
            forbidden_fields(row.get("extract"), false_confidence, f"{entry['id']}.extract")
            rows.append(row)
    finally:
        await service.close()

    summary = summarize(rows)
    summary["init_ms"] = init_ms
    summary["cache_dir"] = str(cache_dir)
    gates = evaluate_gates(
        summary,
        schema["total_tokens"],
        token_violations,
        citation_failures,
        len(false_confidence),
        args,
    )
    result = {
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "dataset": str(Path(args.dataset)),
        "tokenizer": TOKENIZER_NAME,
        "providers": service.router.provider_names,
        "schema": schema,
        "summary": summary,
        "gates": gates,
        "passed": all(g["ok"] for g in gates),
        "violations": {
            "token_budget": token_violations,
            "citations": citation_failures,
            "uncalibrated_fields": false_confidence,
        },
        "rows": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    out.with_suffix(".md").write_text(markdown_report(result), encoding="utf-8")
    print(markdown_report(result))
    print(f"wrote {out} and {out.with_suffix('.md')}", file=sys.stderr)
    return 0 if result["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default="benchmarks/queries.jsonl")
    p.add_argument("--out", default="benchmarks/results/latest.json")
    p.add_argument("--cache-dir", default="benchmarks/.cache")
    p.add_argument("--fresh-cache", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--ids", default="", help="comma-separated dataset ids to run")
    p.add_argument("--categories", default="", help="comma-separated categories to run")
    p.add_argument("--extract-limit", type=int, default=6)
    p.add_argument("--max-schema-tokens", type=int, default=1000)
    p.add_argument("--min-precision", type=float, default=0.25)
    p.add_argument("--min-top3", type=float, default=0.6)
    p.add_argument("--min-support", type=float, default=0.6)
    p.add_argument("--min-noresult", type=float, default=0.75)
    p.add_argument("--max-search-p50", type=float, default=1500)
    p.add_argument("--max-search-p95", type=float, default=5000)
    p.add_argument("--max-extract-p50", type=float, default=2500)
    p.add_argument("--max-extract-p95", type=float, default=8000)
    p.add_argument("--max-research-p95", type=float, default=20000)
    return p


def main() -> int:
    return asyncio.run(main_async(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
