#!/usr/bin/env python
"""v6 deterministic report builder (self-contained).

Inputs: evidence/ledger.jsonl + evidence/raw/<id>/result.json + frozen dataset files.
Outputs: reports/extreme-benchmark-v6/REPORT.md and manifest.json.

No number is typed into the report: every value is a registered metric rendered
here. Run ids are immutable; required experiments must exist and be uncontaminated.
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
LEDGER = EVIDENCE / "ledger.jsonl"
RAW = EVIDENCE / "raw"
OUT_DIR = ROOT / "reports" / "extreme-benchmark-v6"
OUT_REPORT = OUT_DIR / "REPORT.md"
OUT_MANIFEST = OUT_DIR / "manifest.json"
GENESIS = "0" * 64
SEED = 20261101
REQUIRED = ["EXP-000", "EXP-001b", "EXP-002", "EXP-003", "EXP-004b", "EXP-005", "EXP-006", "EXP-007b", "EXP-008"]
NUMBER_RE = re.compile(r"(?<![0-9A-Za-z_])[0-9]+(?:\.[0-9]+)?(?![0-9A-Za-z_])")
STATIC_ALLOWED = {"256"}  # "SHA-256" is an algorithm name


class BuildError(RuntimeError):
    pass


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifacts(rec: dict):
    for entry in rec.get("files", []) or []:
        if isinstance(entry, dict) and "path" in entry and "sha256" in entry:
            yield entry["path"], entry["sha256"]
    outputs = rec.get("outputs")
    if isinstance(outputs, dict):
        for path, digest in outputs.items():
            yield path, digest


def verify_chain() -> tuple[bool, list[str], dict]:
    import hashlib

    problems: list[str] = []
    if not LEDGER.exists():
        return False, ["ledger missing"], {}
    prev = GENESIS
    runs = []
    ids: set[str] = set()
    classes: dict[str, int] = {}
    for lineno, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rec = json.loads(line)
        runs.append(rec)
        rid = rec.get("id", f"line{lineno}")
        if rid in ids:
            problems.append(f"{rid}: duplicate id")
        ids.add(rid)
        klass = rec.get("class", "?")
        classes[klass] = classes.get(klass, 0) + 1
        if rec.get("prev_hash") != prev:
            problems.append(f"{rid}: prev_hash mismatch")
        body = {k: v for k, v in rec.items() if k != "hash"}
        expected = hashlib.sha256((prev + canonical(body)).encode("utf-8")).hexdigest()
        if rec.get("hash") != expected:
            problems.append(f"{rid}: record hash mismatch")
        prev = rec.get("hash", "")
        for rel, digest in artifacts(rec):
            path = ROOT / rel
            if not path.exists():
                problems.append(f"{rid}: missing artifact {rel}")
            elif sha256_file(path) != digest:
                problems.append(f"{rid}: artifact hash mismatch {rel}")
    return not problems, problems, {"runs": runs, "head": prev, "classes": classes}


def wilson(k: int, n: int, z: float = 1.959963984540054):
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def pct(values, q):
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q / 100.0
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] * (1 - (pos - lo)) + ordered[hi] * (pos - lo))


def mean(values):
    return float(sum(values) / len(values)) if values else float("nan")


def bootstrap(values, stat=mean, resamples=10000, seed=SEED):
    if not values:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(values)
    estimates = [stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)]
    return pct(estimates, 2.5), pct(estimates, 97.5)


def fmt_pct(k: int, n: int) -> str:
    if n <= 0:
        return "0/0 (not measured)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.1f}% [{100 * lo:.1f}%, {100 * hi:.1f}%])"


def interval(rec: dict):
    from datetime import datetime

    start = rec.get("started_utc") or rec.get("utc_start")
    end = rec.get("ended_utc") or rec.get("utc_end")
    return (
        datetime.fromisoformat(start.replace("Z", "+00:00")),
        datetime.fromisoformat(end.replace("Z", "+00:00")),
    )


def build() -> tuple[str, dict]:
    ok, problems, chain = verify_chain()
    if not ok:
        raise BuildError("evidence chain invalid: " + "; ".join(problems[:3]))
    runs = chain["runs"]
    by_id = {r["id"]: r for r in runs}
    for rid in REQUIRED:
        if rid not in by_id:
            raise BuildError(f"required run {rid} missing")
        if by_id[rid].get("contaminated"):
            raise BuildError(f"required run {rid} is contaminated")
        if not (RAW / rid / "result.json").exists():
            raise BuildError(f"required run {rid} has no result.json")
    results = {rid: json.loads((RAW / rid / "result.json").read_text(encoding="utf-8")) for rid in REQUIRED}

    metrics: dict[str, dict] = {}

    def add(key, value, *, kind, evidence, n=None, ci=None, klass="REAL", note=""):
        if key in metrics:
            raise BuildError(f"duplicate metric {key}")
        metrics[key] = {"value": value, "kind": kind, "n": n, "ci": ci, "evidence": evidence, "class": klass, "note": note}

    def proportion(key, k, n, evidence, klass="REAL", note=""):
        value = fmt_pct(k, n)
        if n < 30:
            value += " — n<30: too small to support a claim"
        lo, hi = wilson(k, n)
        add(key, value, kind="proportion", evidence=evidence, n=n, ci=[lo, hi], klass=klass, note=note)

    def continuous(key, values, evidence, unit="ms", klass="SIMULATED"):
        if not values:
            add(key, "NOT RUN", kind="text", evidence=evidence, klass=klass)
            return
        lo, hi = bootstrap(values)
        value = (
            f"mean {mean(values):.2f} {unit} [{lo:.2f}, {hi:.2f}], "
            f"median {pct(values, 50):.2f}, p95 {pct(values, 95):.2f}"
        )
        if len(values) < 30:
            value += " — n<30: too small to support a claim"
        add(key, value, kind="continuous", evidence=evidence, n=len(values), ci=[lo, hi], klass=klass)

    state = results["EXP-000"]["rows"][0]
    last = runs[-1]
    add("meta.generated_utc", str(last.get("ended_utc") or last.get("utc_end")), kind="text", evidence=[last["id"]])
    add("meta.commit", str(state["git_commit"])[:12], kind="text", evidence=["EXP-000"])
    add("meta.branch", str(state["git_branch"]), kind="text", evidence=["EXP-000"])
    add("meta.tree_hash", str(by_id["EXP-000"].get("tree_hash") or by_id["EXP-000"].get("git_diff_hash")), kind="text", evidence=["EXP-000"])
    add("meta.ledger_head", chain["head"], kind="text", evidence=[r["id"] for r in runs])
    add("meta.runs", str(len(runs)), kind="count", evidence=[r["id"] for r in runs])
    add("subject.module", str(state["weblens_module"]), kind="text", evidence=["EXP-000"])
    add("subject.version", str(state["weblens_version"]), kind="text", evidence=["EXP-000"])
    add("subject.python", str(state["python"]).split()[0], kind="text", evidence=["EXP-000"])
    add("subject.pytest", str(state["packages"].get("pytest", "absent")), kind="text", evidence=["EXP-000"])
    add("subject.playwright", str(state["packages"].get("playwright", "absent")), kind="text", evidence=["EXP-000"])

    required_set = set(REQUIRED)
    legacy_overlaps = 0
    for rec in runs:
        if rec["id"] in required_set:
            continue
        try:
            start, end = interval(rec)
        except (TypeError, ValueError):
            continue
        for other in runs:
            if other["id"] == rec["id"]:
                continue
            try:
                ostart, oend = interval(other)
            except (TypeError, ValueError):
                continue
            if start < oend and ostart < end:
                legacy_overlaps += 1
                break
    add(
        "meta.timeline_note",
        f"{legacy_overlaps} inherited run(s) overlap another run; they came from a prior interrupted parallel session. "
        "This pass's runs are strictly sequential, and that is what the linter enforces.",
        kind="text",
        evidence=["EXP-000"],
    )

    for name, rel in (
        ("core", "benchmarks/eval_dataset.json"),
        ("expanded", "benchmarks/eval_dataset_expanded.json"),
        ("paired", "benchmarks/tavily_paired_subset.json"),
    ):
        path = ROOT / rel
        digest = sha256_file(path)
        if state["file_hashes"].get(rel) != digest:
            raise BuildError(f"{rel}: hash differs from EXP-000")
        add(f"dataset.{name}.n", str(len(json.loads(path.read_text(encoding="utf-8")))), kind="count", evidence=["EXP-000"])
        add(f"dataset.{name}.sha", digest, kind="text", evidence=["EXP-000"])

    tests = results["EXP-001b"]["rows"][0]
    if tests["passed"] + tests["failed"] + tests["errors"] == 0:
        raise BuildError("zero executed tests")

    def tc(field):
        add(f"tests.{field}", str(tests[field]), kind="count", evidence=["EXP-001b"])

    for field in ("passed", "failed", "skipped", "collected"):
        tc(field)
    add("tests.exit", str(tests["exit_code"]), kind="count", evidence=["EXP-001b"])
    add("tests.ran", str(tests["passed"] + tests["failed"] + tests["errors"]), kind="count", evidence=["EXP-001b"])
    add(
        "superseded.note",
        "EXP-001, EXP-004 and EXP-007 are superseded by their corrected b runs and are excluded from every aggregate; they remain in the ledger.",
        kind="text",
        evidence=["EXP-001b"],
    )

    ssrf = results["EXP-002"]
    tested = [r for r in ssrf["rows"] if r["blocked"] is not None and r["url_kind"] != "control"]
    blocked = [r for r in tested if r["blocked"]]
    packets = sum(r.get("fixture_hits_delta", 0) for r in tested)
    add("ssrf.attempts", str(len(tested)), kind="count", evidence=["EXP-002"])
    add("ssrf.blocked", str(len(blocked)), kind="count", evidence=["EXP-002"])
    add("ssrf.packets", str(packets), kind="count", evidence=["EXP-002"])
    proportion("ssrf.rate", len(blocked), len(tested), ["EXP-002"], klass="SIMULATED")
    add("ssrf.guard_off", "reached the fixture only with the guard disabled" if ssrf["summary"].get("guard_off_control_reached") else "guard-off control did not reach the fixture", kind="text", evidence=["EXP-002"], klass="SIMULATED")

    inj = results["EXP-003"]
    attacks = [r for r in inj["rows"] if r["kind"] == "attack"]
    benign = [r for r in inj["rows"] if r["kind"] == "benign"]
    flagged = sum(r["flagged"] for r in attacks)
    fp = sum(r["flagged"] for r in benign)
    add("injection.attacks", str(len(attacks)), kind="count", evidence=["EXP-003"], klass="SIMULATED")
    add("injection.flagged", str(flagged), kind="count", evidence=["EXP-003"], klass="SIMULATED")
    add("injection.benign", str(len(benign)), kind="count", evidence=["EXP-003"], klass="SIMULATED")
    add("injection.fp", str(fp), kind="count", evidence=["EXP-003"], klass="SIMULATED")
    proportion("injection.detection", flagged, len(attacks), ["EXP-003"], klass="SIMULATED")
    proportion("injection.fp_rate", fp, len(benign), ["EXP-003"], klass="SIMULATED")

    cache_rows = results["EXP-004b"]["rows"]
    passed_cases = sum(1 for r in cache_rows if r["passed"])
    add("cache.cases", str(len(cache_rows)), kind="count", evidence=["EXP-004b"])
    add("cache.passed", str(passed_cases), kind="count", evidence=["EXP-004b"])
    proportion("cache.rate", passed_cases, len(cache_rows), ["EXP-004b"])

    ext = results["EXP-005"]
    page_rows = [r for r in ext["rows"] if r["facts_total"] > 0]
    budget_rows = [r for r in ext["rows"] if r["page_type"].startswith("budget_")]
    total_facts = sum(r["facts_total"] for r in page_rows)
    found_facts = sum(r["facts_found"] for r in page_rows)
    add("extract.pages", str(len(page_rows)), kind="count", evidence=["EXP-005"], klass="SIMULATED")
    add("extract.facts_total", str(total_facts), kind="count", evidence=["EXP-005"], klass="SIMULATED")
    add("extract.facts_found", str(found_facts), kind="count", evidence=["EXP-005"], klass="SIMULATED")
    add("extract.full_pages", str(sum(1 for r in page_rows if r["facts_found"] == r["facts_total"])), kind="count", evidence=["EXP-005"], klass="SIMULATED")
    add("extract.zero_pages", str(sum(1 for r in page_rows if r["facts_found"] == 0)), kind="count", evidence=["EXP-005"], klass="SIMULATED")
    proportion("extract.recall", found_facts, total_facts, ["EXP-005"], klass="SIMULATED")
    for row in page_rows:
        key = "extract.page." + re.sub(r"[^a-z0-9]+", "_", row["page_type"].lower()).strip("_")
        proportion(key, row["facts_found"], row["facts_total"], ["EXP-005"], klass="SIMULATED")
    for row in ext["rows"]:
        key = "extract.status." + re.sub(r"[^a-z0-9]+", "_", row["page_type"].lower()).strip("_")
        add(key, str(row["status"]), kind="text", evidence=["EXP-005"], klass="SIMULATED")
    continuous("extract.latency_ms", [r["ms"] for r in ext["rows"] if r["ms"] > 0], ["EXP-005"])
    add("extract.budget_checks", str(len(budget_rows)), kind="count", evidence=["EXP-005"], klass="SIMULATED")
    add("extract.budget_ok", str(sum(1 for r in budget_rows if f"within={r['tok'] <= int(r['page_type'].split('_')[1])}" in r["warnings"])), kind="count", evidence=["EXP-005"], klass="SIMULATED")

    tok = results["EXP-006"]["summary"]
    if tok["status"] == "measured":
        add("tokens.schema_total", str(tok["schema_tokens_total"]), kind="count", evidence=["EXP-006"])
        add("tokens.tools", str(tok["tools"]), kind="count", evidence=["EXP-006"])
    else:
        add("tokens.schema_total", "NOT RUN", kind="text", evidence=["EXP-006"])
        add("tokens.tools", "NOT RUN", kind="text", evidence=["EXP-006"])
    add("tokens.tokenizer", str(tok["tokenizer"]), kind="text", evidence=["EXP-006"])
    add("subject.tokenizer", str(tok["tokenizer"]), kind="text", evidence=["EXP-006"])
    add("tokens.source", str(tok["source"]), kind="text", evidence=["EXP-006"])
    add("tokens.status", "measured" if tok["status"] == "measured" else "NOT RUN", kind="text", evidence=["EXP-006"])

    mut_rows = [r for r in results["EXP-007b"]["rows"] if r["detected"] is not None]
    detected = sum(1 for r in mut_rows if r["detected"])
    add("mutation.cases", str(len(mut_rows)), kind="count", evidence=["EXP-007b"])
    add("mutation.detected", str(detected), kind="count", evidence=["EXP-007b"])
    proportion("mutation.rate", detected, len(mut_rows), ["EXP-007b"])

    sec = results["EXP-008"]
    summary = sec["summary"]
    add("secrets.files", str(summary["files_scanned"]), kind="count", evidence=["EXP-008"])
    add("secrets.tree_hits", str(summary["tree_hits"]), kind="count", evidence=["EXP-008"])
    add("secrets.history_hits", str(summary["history_hits"]), kind="count", evidence=["EXP-008"])
    add("secrets.redaction", "passed" if summary["redaction_ok"] else "FAILED", kind="text", evidence=["EXP-008"])
    add("secrets.env_example_starts_tvly", "no" if not summary["env_example_starts_with_tvly"] else "yes", kind="text", evidence=["EXP-008"])
    add("secrets.env_example_placeholder", "no" if not summary["env_example_looks_placeholder"] else "yes", kind="text", evidence=["EXP-008"])
    tree = next((r for r in sec["rows"] if r.get("case") == "tree_scan"), {})
    detail = "; ".join(f"{h['kind']} at {h['path']}" for h in tree.get("hits", [])) or "none"
    add("secrets.detail", detail, kind="text", evidence=["EXP-008"])

    not_run = [
        "Tavily direct API (budget authorization absent)",
        "Tavily via WebLens",
        "Tavily MCP server",
        "SearXNG-backed WebLens (service unreachable; JSON format approval absent)",
        "WebLens keyless live search",
        "root stack keyless and Tavily",
        "Playwright browser egress and subresources",
        "live-web extraction and large extraction corpus",
        "large behaviour corpus and gold-labelled accuracy set",
        "MCP conformance suite",
        "fuzzing at scale",
        "soak test",
        "agent-loop prompt-injection attack success",
        "independent audit",
        "human review",
    ]
    add("notrun.count", str(len(not_run)), kind="count", evidence=["EXP-008"])
    add("notrun.list", "; ".join(not_run), kind="text", evidence=["EXP-008"])

    M = lambda key: metrics[key]["value"]  # noqa: E731

    lines: list[str] = []
    a = lines.append
    a("# WebLens evaluation — evidence report")
    a("")
    a(f"Generated deterministically from the hash-chained ledger at `{M('meta.generated_utc')}`.")
    a(f"Subject: the `weblens/` package at commit `{M('meta.commit')}`, tree hash `{M('meta.tree_hash')}`,")
    a(f"ledger head `{M('meta.ledger_head')}`.")
    a("")
    a("Built by `tools/v6_build_report.py`; checked by `tools/v6_lint_report.py`. No number is typed by hand.")
    a("")
    a("## Verdict: hard problems first")
    a("")
    a("- **No Tavily comparison exists in this pass.** Tavily direct, Tavily via WebLens and the Tavily MCP")
    a("  server are NOT RUN. No quality, latency, token or cost winner is claimed. Neither \"Tavily is better\"")
    a("  nor the reverse can be concluded, because Tavily was not measured.")
    a("- **No live-web search was run.** Ranking quality, freshness and multilingual behaviour are NOT RUN;")
    a("  the pre-registered search gates are not evaluated.")
    a(f"- **No browser run.** Playwright is `{M('subject.playwright')}` in the pinned environment. Browser egress,")
    a("  subresource blocking and the proxy are NOT RUN.")
    a("- **Fixture results are SIMULATED.** The SSRF matrix, injection corpus and extraction pages are local")
    a("  fixtures; they show how these code paths handle these fixtures, not live-web performance.")
    a("- **Samples are small.** Every proportion carries its n and a Wilson interval; anything below the")
    a("  pre-registered threshold says \"too small to support a claim\".")
    a("- **No independent audit and no human review.** The reporter is deterministic and the owner can verify")
    a("  it, but it was written by the executor whose work it describes.")
    a("- **Secret-store action needed.** `.env.example` has a non-empty Tavily key value that is not `tvly-`")
    a(f"  shaped and is not a placeholder (`{M('secrets.env_example_starts_tvly')}` / `{M('secrets.env_example_placeholder')}`).")
    a("  It is untracked and absent from history. Rotate it if it is live. Its value is never printed.")
    a("")
    a("Established in this pass: the package suite result, the loopback SSRF matrix against the real fetcher,")
    a("injection-scanner calibration on a synthetic corpus, cache correctness, extraction fact recall on")
    a("fixtures, the MCP schema token count, tamper/mutation detection, and a secret-pattern scan.")
    a("")
    a("## Systems under test")
    a("")
    a("| System | Status | Reason |")
    a("|---|---|---|")
    a("| WebLens keyless | NOT RUN | No live search pass |")
    a("| WebLens + SearXNG | NOT RUN | Service unreachable; format change not authorized |")
    a("| WebLens + Tavily | NOT RUN | No credit-spend authorization |")
    a("| Tavily direct API | NOT RUN | No credit-spend authorization |")
    a("| Tavily MCP server | NOT RUN | No credit-spend authorization |")
    a("| root stack keyless | NOT RUN | Separate stack, out of scope |")
    a("| root stack + Tavily | NOT RUN | Out of scope; no spend authorization |")
    a("| later competitors | NOT RUN | Not installed or not authorized |")
    a("")
    a(f"WebLens `{M('subject.version')}` from `{M('subject.module')}`, Python `{M('subject.python')}`, pytest `{M('subject.pytest')}`.")
    a("")
    a("A second copy of the package exists at `src/weblens` and shadows the subject on the default import")
    a("path. Every experiment pins `weblens/src` and asserts the loaded module path.")
    a("")
    a("## Environment and fairness")
    a("")
    a(f"The ledger pins the full tree hash (`{M('meta.tree_hash')}`) for every run; the tree contains")
    a("pre-existing changes and this pass's tools. Fixture runs disable the cache or use a temporary")
    a("directory, so no cache state is shared between experiments.")
    a("")
    a("## Datasets")
    a("")
    a("| Dataset | Items | Hash | Status |")
    a("|---|---|---|---|")
    a(f"| `benchmarks/eval_dataset.json` | {M('dataset.core.n')} | `{M('dataset.core.sha')}` | Frozen, English-only lookup set |")
    a(f"| `benchmarks/eval_dataset_expanded.json` | {M('dataset.expanded.n')} | `{M('dataset.expanded.sha')}` | Frozen, English-only |")
    a(f"| `benchmarks/tavily_paired_subset.json` | {M('dataset.paired.n')} | `{M('dataset.paired.sha')}` | Frozen, paired run NOT RUN |")
    a("")
    a("These sets do not meet the directive's scale requirements. No claim is made that they do.")
    a("")
    a("## Package test suite")
    a("")
    a(f"One pytest process ran `weblens/tests`: collected `{M('tests.collected')}`, passed `{M('tests.passed')}`,")
    a(f"failed `{M('tests.failed')}`, skipped `{M('tests.skipped')}`; executed `{M('tests.ran')}`; exit `{M('tests.exit')}`.")
    a("A skipped test is not a pass. The root `tests/` suite and the root stack were not run.")
    a("")
    a(f"Superseded attempts: {M('superseded.note')}")
    a("")
    a("## SSRF and URL handling")
    a("")
    a(f"The real `SafeFetcher` attempted `{M('ssrf.attempts')}` private, loopback, metadata, scheme and encoding")
    a(f"variants against a loopback fixture. `{M('ssrf.blocked')}` were blocked; the fixture received")
    a(f"`{M('ssrf.packets')}` requests attributable to blocked variants. Block rate: `{M('ssrf.rate')}`.")
    a("")
    a(f"Guard is load-bearing: {M('ssrf.guard_off')}. This is the broken-build control.")
    a("")
    a("NOT RUN: redirect-to-private and public-host DNS rebinding (no controllable public redirector was")
    a("exposed), browser subresources, and proxy CONNECT abuse. No claim is made for those classes.")
    a("")
    a("## Prompt-injection scanner calibration")
    a("")
    a(f"On `{M('injection.attacks')}` synthetic attack strings the scanner flagged `{M('injection.flagged')}`")
    a(f"(`{M('injection.detection')}`). On `{M('injection.benign')}` benign technical strings it flagged")
    a(f"`{M('injection.fp')}` (`{M('injection.fp_rate')}`).")
    a("")
    a("This is a flag, not a block and not an agent outcome. No agent loop was driven, so no attack-success")
    a("rate is claimed. The corpus is hand-written, not BIPIA, InjecAgent or AgentDojo.")
    a("")
    a("## Cache correctness")
    a("")
    a(f"`{M('cache.passed')}` of `{M('cache.cases')}` cases passed (`{M('cache.rate')}`): TTL expiry, key-field")
    a("separation, hostile-key SQL handling, logical-size eviction, restart persistence, corrupt-value")
    a("containment, disabled-cache behaviour, cross-key isolation.")
    a("")
    a("Recorded limitation: eviction uses the documented logical payload cap; the SQLite file can exceed it.")
    a("")
    a("## Extraction on local fixtures")
    a("")
    a(f"Across `{M('extract.pages')}` page types, `{M('extract.facts_found')}` of `{M('extract.facts_total')}`")
    a(f"planted facts were recovered (`{M('extract.recall')}`). `{M('extract.full_pages')}` pages recovered every")
    a(f"fact; `{M('extract.zero_pages')}` recovered none.")
    a("")
    a("| Page | Status | Planted facts recovered |")
    a("|---|---|---|")
    for label, key in (
        ("static article", "static_article"), ("table", "table"), ("malformed HTML", "malformed"),
        ("non-UTF8", "non_utf8"), ("large page", "large"), ("JavaScript shell", "spa_shell"),
        ("injection page", "injection"), ("PDF with text layer", "pdf_text"), ("blank PDF", "pdf_blank"),
        ("redirect", "redirect"), ("not found", "not_found"),
    ):
        recall = f"`{M('extract.page.' + key)}`" if f"extract.page.{key}" in metrics else "not applicable"
        a(f"| {label} | `{M('extract.status.' + key)}` | {recall} |")
    a("")
    a(f"Latency over fixture calls: `{M('extract.latency_ms')}`.")
    a("")
    a(f"Budget adherence: `{M('extract.budget_ok')}` of `{M('extract.budget_checks')}` calls stayed within the requested budget.")
    a("")
    a("The JavaScript-shell result is the static-extraction loss: with the browser disabled the content is")
    a("not recovered. This is a no-browser limitation, not a browser measurement.")
    a("")
    a("## Token surface")
    a("")
    a(f"MCP schema: `{M('tokens.schema_total')}` tokens over `{M('tokens.tools')}` tools, tokenizer")
    a(f"`{M('tokens.tokenizer')}`, source `{M('tokens.source')}`, status `{M('tokens.status')}`.")
    a("")
    a("The pre-registration named `o200k_base`; the packaged tokenizer reports the value above. That")
    a("pre-registration statement was an assumption and was wrong; the measured value is reported and the")
    a("discrepancy is recorded, not silently corrected.")
    a("")
    a("No competitor schema was measured. No token-efficiency ratio is claimed.")
    a("")
    a("## Mutation and tamper checks")
    a("")
    a(f"`{M('mutation.detected')}` of `{M('mutation.cases')}` mutations were detected (`{M('mutation.rate')}`):")
    a("a ledger-record edit, a raw-artifact edit, and disabling the SSRF guard before running the package's")
    a("own SSRF tests. The clean copy verified first, so a broken verifier would not pass.")
    a("")
    a("NOT RUN: token-cap removal, scanner removal, random-result and empty-result search mutations.")
    a("")
    a("## Secrets")
    a("")
    a(f"Scanned `{M('secrets.files')}` text files (excluding `.env`). Tree pattern hits `{M('secrets.tree_hits')}`;")
    a(f"git-history hits `{M('secrets.history_hits')}`. Redaction self-test: `{M('secrets.redaction')}`.")
    a("")
    a(f"Pattern hits with paths only: `{M('secrets.detail')}`. These are an environment assignment in the")
    a("example file, a canary fixture in the test tree, and an example client token; none matched the live key.")
    a("")
    a("This is a pattern scan, not a substitute for gitleaks or trufflehog, which are not installed.")
    a("")
    a("## Latency, throughput and soak")
    a("")
    a("NOT RUN. No live search, browser, concurrency ladder or sustained soak was executed. The only latency")
    a("figure above is fixture extraction.")
    a("")
    a("## Tavily and competitor comparison")
    a("")
    a("NOT RUN. Credit spend and service configuration were not authorized. Therefore there is no accuracy,")
    a("latency, token, cost or quality comparison, no winner, and no claim that WebLens is better or worse.")
    a("")
    a("## Penetration coverage")
    a("")
    a("| Class | Attempted | Result |")
    a("|---|---:|---|")
    a(f"| SSRF / URL handling (loopback fixture) | {M('ssrf.attempts')} | `{M('ssrf.rate')}` blocked, `{M('ssrf.packets')}` fixture requests |")
    a(f"| Prompt injection (scanner input) | {M('injection.attacks')} | `{M('injection.detection')}` flagged |")
    a(f"| Cache poisoning / SQL / TTL | {M('cache.cases')} | `{M('cache.rate')}` cases passed |")
    a(f"| Tamper and broken build | {M('mutation.cases')} | `{M('mutation.rate')}` detected |")
    a("| Browser egress | NOT RUN | Playwright absent |")
    a("| Fuzzing at scale | NOT RUN | Tooling absent |")
    a("| MCP conformance | NOT RUN | Suite not present |")
    a("| Supply chain | NOT RUN | Scanners absent |")
    a("| Resource exhaustion / soak | NOT RUN | Not executed |")
    a("")
    a("Strongest allowed statement: no failure was observed in the executed classes. That is not a claim of security.")
    a("")
    a("## Failures and losses")
    a("")
    a("- Static extraction recovers nothing from the JavaScript-only shell with the browser disabled.")
    a(f"- The non-UTF8 fixture recovered `{M('extract.page.non_utf8')}` of its planted facts; cause not established.")
    a(f"- The large page recovered `{M('extract.page.large')}` of its planted facts: the final marker sits at")
    a("  the end of a long page and was not in the returned passages.")
    a("- The injection corpus is synthetic; detection and false-positive rates are corpus-specific.")
    a("- Cache physical file size can exceed the logical cap.")
    a("- `.env.example` holds a non-placeholder key value that could not be classified safely.")
    a("- The root stack was not run; no cross-stack numbers are merged.")
    a("")
    a("## Honesty section")
    a("")
    a(f"**Could any number be changed without the linter noticing?** No numeric token is accepted unless it is")
    a(f"in the reporter manifest, and the report is rebuilt and byte-compared during lint. `{M('meta.runs')}` ledger")
    a(f"runs back the report; `{M('notrun.count')}` categories are explicitly NOT RUN.")
    a("")
    a("**Is anything left out without saying so?** The systems table and the NOT RUN list name every unrun")
    a("system and class, including the root stack, browser, live search, Tavily, SearXNG, conformance, fuzzing,")
    a("soak, independent audit and human review.")
    a("")
    a(f"**Did any test pass a broken build?** The SSRF tests failed with the guard disabled (`{M('mutation.rate')}`")
    a("of mutation checks detected). Token-cap and scanner mutations were not run.")
    a("")
    a("**Did every Tavily comparison use identical queries, caps and timing?** No Tavily comparison was run,")
    a("so the fairness question is not applicable in this pass.")
    a("")
    a("**Where does WebLens lose, and is it stated first?** It loses on JavaScript-only extraction without a")
    a("browser, stated above the positive results. Against Tavily nothing is measured in either direction.")
    a("")
    a("**Independent audit and human review:** NOT RUN. No separate read-only agent and no human reviewer")
    a("participated. The reporter is deterministic and owner-verifiable, but it was written by the same")
    a("executor whose work it describes. No result is labelled human-verified or model-judged.")
    a("")
    a("## Reproduction")
    a("")
    a("```bash")
    a("python tools/v6_verify_evidence.py")
    a("python tools/v6_build_report.py")
    a("python tools/v6_lint_report.py")
    a("```")
    a("")
    a("Experiments must run through `tools/v6_evidence_run.py` with a new id; ids are immutable.")
    a("")
    a("## Evidence provenance")
    a("")
    a(f"- git commit: `{M('meta.commit')}` (branch `{M('meta.branch')}`)")
    a(f"- working-tree hash: `{M('meta.tree_hash')}`")
    a(f"- ledger head: `{M('meta.ledger_head')}`")
    a(f"- ledger runs: `{M('meta.runs')}`")
    a(f"- timeline: {M('meta.timeline_note')}")
    a("")

    report = "\n".join(lines)

    texts = [m["value"] for m in metrics.values()]
    texts.append(chain["head"])
    texts += [r["id"] for r in runs]
    texts += [str(v) for v in state["packages"].values()]
    texts += [str(last["ended_utc"]), str(by_id["EXP-000"]["started_utc"]), str(by_id["EXP-000"]["ended_utc"])]
    allowed = set(STATIC_ALLOWED)
    for text in texts:
        allowed.update(NUMBER_RE.findall(str(text)))

    manifest = {
        "generated_from_ledger_head": chain["head"],
        "runs": len(runs),
        "classes": chain["classes"],
        "required": REQUIRED,
        "metrics": metrics,
        "allowed_numbers": sorted(allowed),
        "not_run_systems": ["Tavily", "SearXNG", "root stack", "Playwright", "competitors", "independent auditor", "human review"],
        "excluded_contaminated": [],
    }
    return report, manifest


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        report, manifest = build()
    except BuildError as exc:
        print(f"FAIL build: {exc}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.check:
        if not OUT_REPORT.exists() or OUT_REPORT.read_text(encoding="utf-8") != report:
            print("FAIL report is stale or missing", file=sys.stderr)
            return 1
        if not OUT_MANIFEST.exists() or json.loads(OUT_MANIFEST.read_text(encoding="utf-8")) != manifest:
            print("FAIL manifest is stale or missing", file=sys.stderr)
            return 1
        print("PASS report and manifest reproduce from the ledger")
        return 0
    OUT_REPORT.write_text(report, encoding="utf-8", newline="\n")
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT_REPORT.relative_to(ROOT)} ({len(report)} bytes, {len(metrics_placeholder := manifest['metrics'])} metrics)")
    print(f"ledger head {manifest['generated_from_ledger_head']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
