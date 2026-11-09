"""Strict cross-model verification battery for the WebLens engine.

Purpose
-------
Exercise the codebase top to bottom with each configured model (Qwen, Gemma,
Mistral, Gemini) and assert hard contracts instead of inspecting output by eye.

Layers exercised
----------------
1. credential  - is a model id + credential actually configured?
2. reachability- live minimal call; a model that 4xx/5xx/times out is BLOCKED
3. contract    - exact-instruction, JSON schema, usage accounting, latency ceiling
4. grounding   - citation integrity and no-fabrication on an empty evidence set
5. engine e2e  - server.web_search -> server.extract_url -> synthesis over the
                 real extracted text (live keyless providers, no paid credits)

Exit codes
----------
0  every requested model passed every check
1  at least one check FAILED (real defect)
2  no failures, but at least one model was BLOCKED (unreachable/not configured)

Exit 2 exists so a blocked model can never be mistaken for a passing one. There
is no flag that turns a FAIL into a PASS, and no check is skipped when a model
is reachable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow execution as `python scripts/cross_model_verification.py` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import CONFIG  # noqa: E402
from model_provider import ModelProvider, model_client  # noqa: E402

ARTIFACT_DIR = Path("reports/cross-model")

LATENCY_CEILING_MS = 30_000.0

TARGET_MODELS: dict[str, str] = {
    "qwen": CONFIG.qwen_model,
    "gemma": CONFIG.gemma_model,
    "mistral": "mistralai/mistral-large-4-1t-a52b",
    "gemini": "gemini-3.5-flash",
}

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).strip(" .,:;!\"'`*#")


def _check(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"check": name, "status": status, "detail": detail, **extra}


async def probe_reachability(model: str) -> tuple[bool, str]:
    """Live minimal call. Any non-200, empty content or exception blocks the model."""
    try:
        res = await asyncio.wait_for(
            model_client.generate(
                prompt="Reply with exactly: PONG",
                model=model,
                max_tokens=16,
                temperature=0.0,
            ),
            timeout=45,
        )
    except TimeoutError:
        return False, "probe timeout after 45s"
    except Exception as e:  # noqa: BLE001 - reported, never swallowed silently
        return False, f"probe raised {type(e).__name__}: {e}"

    if res.provider is ModelProvider.LOCAL_ALGORITHMIC:
        # The deterministic local synthesizer answers anything, so reaching it
        # proves nothing about the requested model.
        return False, "fell through to local algorithmic synthesizer (model never served the request)"
    if not res.content.strip():
        return False, f"empty content from {res.provider}"
    # A fallback chain that answers with a *different* model must not count as
    # reaching the requested one.
    if res.model_name != model or res.provider is not model_client.model_family(model):
        return False, (
            f"requested {model}, but answer came from {res.model_name} via {res.provider} "
            "(fallback, not the requested model)"
        )
    return True, f"HTTP 200 via {res.provider} in {res.latency_ms:.0f} ms ({_norm(res.content)[:40]!r})"


async def contract_checks(model: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # C1 exact instruction compliance
    try:
        res = await asyncio.wait_for(
            model_client.generate(
                prompt="Reply with exactly this token and nothing else: PONG",
                model=model,
                max_tokens=16,
                temperature=0.0,
            ),
            timeout=60,
        )
        ok = _norm(res.content).upper() == "PONG"
        checks.append(
            _check(
                "exact_instruction",
                "PASS" if ok else "FAIL",
                f"expected 'PONG', got {_norm(res.content)[:80]!r}",
            )
        )
        # C3 usage accounting (from the same call, no extra cost)
        usage_ok = (
            res.prompt_tokens > 0
            and res.completion_tokens > 0
            and res.model_name == model
            and res.latency_ms >= 0
        )
        checks.append(
            _check(
                "usage_accounting",
                "PASS" if usage_ok else "FAIL",
                f"prompt={res.prompt_tokens} completion={res.completion_tokens} "
                f"model_name={res.model_name!r} latency_ms={res.latency_ms}",
            )
        )
        checks.append(
            _check(
                "latency_ceiling",
                "PASS" if res.latency_ms <= LATENCY_CEILING_MS else "FAIL",
                f"{res.latency_ms:.0f} ms vs ceiling {LATENCY_CEILING_MS:.0f} ms",
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("exact_instruction", "FAIL", f"raised {type(e).__name__}: {e}"))
        checks.append(_check("usage_accounting", "FAIL", "no result to account"))
        checks.append(_check("latency_ceiling", "FAIL", "no result to time"))

    # C2 strict JSON contract
    try:
        res = await asyncio.wait_for(
            model_client.generate(
                prompt=(
                    'Return only minified JSON matching exactly {"status":"ok","count":3}. '
                    "No prose, no code fences."
                ),
                model=model,
                max_tokens=64,
                temperature=0.0,
            ),
            timeout=60,
        )
        raw = re.sub(r"^```(?:json)?|```$", "", _norm(res.content)).strip()
        match = re.search(r"\{.*\}", raw)
        parsed = json.loads(match.group(0)) if match else None
        ok = isinstance(parsed, dict) and parsed.get("status") == "ok" and parsed.get("count") == 3
        checks.append(
            _check(
                "json_contract",
                "PASS" if ok else "FAIL",
                f"parsed={parsed!r} from {_norm(res.content)[:80]!r}",
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("json_contract", "FAIL", f"raised {type(e).__name__}: {e}"))

    # C4 determinism at temperature 0
    try:
        prompt = "Name one primary colour. One word only."
        first, second = await asyncio.gather(
            model_client.generate(prompt=prompt, model=model, max_tokens=16, temperature=0.0),
            model_client.generate(prompt=prompt, model=model, max_tokens=16, temperature=0.0),
        )
        ok = _norm(first.content).lower() == _norm(second.content).lower()
        checks.append(
            _check(
                "determinism_temp0",
                "PASS" if ok else "FAIL",
                f"{_norm(first.content)[:40]!r} vs {_norm(second.content)[:40]!r}",
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("determinism_temp0", "FAIL", f"raised {type(e).__name__}: {e}"))

    # C5 citation integrity: every source URL cited, no invented URLs
    sources = [
        {
            "title": "Alpha Source",
            "url": "https://alpha.example.org/report-2026",
            "content": "The alpha benchmark measured 42.0 units under standard load in 2026.",
        },
        {
            "title": "Beta Source",
            "url": "https://beta.example.org/findings",
            "content": "Beta findings confirm the alpha benchmark at 42.0 units, with 3 repetitions.",
        },
    ]
    try:
        res = await asyncio.wait_for(
            model_client.synthesize_research_report(
                prompt="Summarise the 2026 benchmark result.", sources=sources, model=model
            ),
            timeout=120,
        )
        text = res.content or ""
        cited = set(URL_RE.findall(text))
        allowed = {s["url"] for s in sources}
        missing = [s["url"] for s in sources if s["url"] not in text]
        invented = sorted(cited - allowed)
        ok = not missing and not invented
        checks.append(
            _check(
                "citation_integrity",
                "PASS" if ok else "FAIL",
                f"missing_citations={missing} invented_urls={invented}",
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("citation_integrity", "FAIL", f"raised {type(e).__name__}: {e}"))

    # C6 no fabricated sources when the evidence set is empty
    try:
        res = await asyncio.wait_for(
            model_client.synthesize_research_report(
                prompt="Summarise the 2026 benchmark result.", sources=[], model=model
            ),
            timeout=120,
        )
        urls = URL_RE.findall(res.content or "")
        ok = not urls
        checks.append(
            _check(
                "no_fabrication_empty_evidence",
                "PASS" if ok else "FAIL",
                f"urls_without_evidence={urls[:3]}",
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("no_fabrication_empty_evidence", "FAIL", f"raised {type(e).__name__}: {e}"))

    return checks


async def engine_e2e(model: str) -> list[dict[str, Any]]:
    """search -> extract -> synthesis over extracted text, through the server tools."""
    import server

    checks: list[dict[str, Any]] = []
    try:
        search_raw = await asyncio.wait_for(
            server.web_search(query="python asyncio timeout best practices", max_results=3),
            timeout=120,
        )
        envelope = json.loads(search_raw)
        results = envelope.get("results") or envelope.get("data") or []
        ok = isinstance(results, list) and len(results) >= 1
        checks.append(_check("e2e_search", "PASS" if ok else "FAIL", f"{len(results)} results"))
        if not ok:
            checks.append(_check("e2e_extract", "FAIL", "no search result to extract"))
            checks.append(_check("e2e_synthesis", "FAIL", "no extracted text"))
            return checks
    except Exception as e:  # noqa: BLE001
        checks.append(_check("e2e_search", "FAIL", f"raised {type(e).__name__}: {e}"))
        checks.append(_check("e2e_extract", "FAIL", "search failed"))
        checks.append(_check("e2e_synthesis", "FAIL", "search failed"))
        return checks

    url = results[0].get("url", "")
    try:
        extract_raw = await asyncio.wait_for(
            server.extract_url(url=url, query="asyncio timeout"), timeout=150
        )
        doc = json.loads(extract_raw)
        text = doc.get("content") or doc.get("text") or ""
        ok = bool(url) and len(text.strip()) >= 200
        checks.append(
            _check("e2e_extract", "PASS" if ok else "FAIL", f"{len(text)} chars from {url}")
        )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("e2e_extract", "FAIL", f"raised {type(e).__name__}: {e}"))
        text = ""

    try:
        res = await asyncio.wait_for(
            model_client.synthesize_research_report(
                prompt="Summarise asyncio timeout practices.",
                sources=[{"title": url or "source", "url": url, "content": text[:4000]}],
                model=model,
            ),
            timeout=150,
        )
        ok = bool(res.content.strip()) and (url in res.content or not url)
        checks.append(
            _check(
                "e2e_synthesis",
                "PASS" if ok else "FAIL",
                f"{len(res.content)} chars via {res.provider}",
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(_check("e2e_synthesis", "FAIL", f"raised {type(e).__name__}: {e}"))

    return checks


async def verify_model(name: str, model: str) -> dict[str, Any]:
    readiness = model_client.model_readiness().get(name, {})
    result: dict[str, Any] = {"name": name, "model": model, "checks": []}

    if not readiness.get("ready", False):
        result["status"] = "BLOCKED"
        result["checks"].append(
            _check("credential", "BLOCKED", readiness.get("blocked_reason") or "not configured")
        )
        return result

    reachable, detail = await probe_reachability(model)
    if not reachable:
        result["status"] = "BLOCKED"
        result["checks"].append(_check("reachability", "BLOCKED", detail))
        return result

    result["checks"].append(_check("reachability", "PASS", detail))
    result["checks"].extend(await contract_checks(model))
    result["checks"].extend(await engine_e2e(model))

    failures = [c for c in result["checks"] if c["status"] == "FAIL"]
    result["status"] = "FAIL" if failures else "PASS"
    return result


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Strict cross-model verification",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Verdict: **{payload['verdict']}**",
        f"- Models requested: {', '.join(payload['requested'])}",
        "",
        "| Model | Model id | Status | Failing checks |",
        "|---|---|---|---|",
    ]
    for r in payload["models"]:
        failing = [c["check"] for c in r["checks"] if c["status"] == "FAIL"]
        lines.append(
            f"| {r['name']} | `{r['model']}` | **{r['status']}** | {', '.join(failing) or '-'} |"
        )
    lines += ["", "## Per-check detail", ""]
    for r in payload["models"]:
        lines.append(f"### {r['name']} — {r['status']}")
        lines.append("")
        lines.append("| Check | Status | Detail |")
        lines.append("|---|---|---|")
        for c in r["checks"]:
            lines.append(f"| {c['check']} | {c['status']} | {c['detail']} |")
        lines.append("")
    return "\n".join(lines) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    requested = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in requested if m not in TARGET_MODELS]
    if unknown:
        print(f"unknown model keys: {unknown}; valid: {sorted(TARGET_MODELS)}", file=sys.stderr)
        return 1

    started = time.perf_counter()
    results = []
    for name in requested:
        print(f"[battery] {name}: {TARGET_MODELS[name]} ...", flush=True)
        results.append(await verify_model(name, TARGET_MODELS[name]))
        print(f"[battery] {name}: {results[-1]['status']}", flush=True)

    failures = [r for r in results if r["status"] == "FAIL"]
    blocked = [r for r in results if r["status"] == "BLOCKED"]
    verdict = "FAIL" if failures else ("BLOCKED" if blocked else "PASS")

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_s": round(time.perf_counter() - started, 2),
        "requested": requested,
        "verdict": verdict,
        "models": results,
        "exit_code": 1 if failures else (2 if blocked else 0),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    json_path = ARTIFACT_DIR / f"battery_{stamp}.json"
    md_path = ARTIFACT_DIR / f"battery_{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print()
    for r in results:
        failing = [c["check"] for c in r["checks"] if c["status"] == "FAIL"]
        blocked_reason = next(
            (c["detail"] for c in r["checks"] if c["status"] == "BLOCKED"), ""
        )
        print(
            f"{r['name']:<8} {r['status']:<8} {r['model']:<40} "
            f"{('failing=' + ','.join(failing)) if failing else blocked_reason}"
        )
    print(f"\nVERDICT {verdict} | duration {payload['duration_s']}s | {json_path}")

    # server.web_search records events, which opens an aiosqlite worker thread;
    # without this the interpreter hangs after the summary is printed.
    try:
        import server

        await server.shutdown_services()
    except Exception as e:  # noqa: BLE001
        print(f"[battery] shutdown warning: {type(e).__name__}: {e}", file=sys.stderr)

    return payload["exit_code"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default=",".join(TARGET_MODELS),
        help=f"comma separated model keys, valid: {sorted(TARGET_MODELS)}",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
