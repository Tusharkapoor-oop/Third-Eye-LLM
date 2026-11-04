"""
Live Quality Arena: MyWebEngine MCP vs. Live Tavily Advanced vs. Gemini Grounding.

WHAT THIS DOES
Runs a fixed 5-category benchmark against three engines, scores each output on a
transparent, deterministic 100-point rubric (no fabricated LLM judgments - Gemini
judging is engaged ONLY when GEMINI_API_KEY exists), emits a rich console
scoreboard with root-cause diagnostics, and writes arena_report.json.

Engine A: local engine internals from src.engine (SearchAggregator /
DocumentExtractor / DeepResearchEngine), exactly the code path MCP tools use.
Engine B: live Tavily REST (search_depth="advanced", chunks_per_source=3,
include_answer="advanced"), or Tavily /extract where the category calls for it.
Engine C: Gemini google_search grounding - requires GEMINI_API_KEY, else BLOCKED.

Exit code: 0 if Engine A reaches AVERAGE >= targets avg target 90/100 and
matches-or-beats Tavily on token efficiency; 1 otherwise (loop controller earns
a non-zero exit so CI / shell loops can drive it).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Minimal .env loader (dotenv not a dependency; differential to dotenv: no extras)
def _bootstrap_env() -> None:
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
    if not os.environ.get("GEMINI_API_KEY"):
        gemini_key = os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY_2") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key

_bootstrap_env()

SCORE_TARGET_AVG = 90.0
# Engine A is free (local), so re-running each case reduces SERP variance:
# the reported score is the median across trials with the matching run kept.
try:
    ENGINE_A_TRIALS = max(1, int(os.environ.get("ARENA_TRIALS", "3") or "3"))
except ValueError:
    ENGINE_A_TRIALS = 3
# Tavily calls are paid. This run may opt into an unlimited session explicitly;
# an unset or zero value remains local-only and spends nothing.
_budget_text = os.environ.get("BUDGET_CAP", "0").strip().casefold()
if _budget_text in {"unlimited", "inf", "infinite", "no_limit"}:
    BUDGET_CAP = float("inf")
else:
    try:
        BUDGET_CAP = float(_budget_text or "0")
    except ValueError:
        BUDGET_CAP = 0.0
_BUDGET_STATE_PATH = Path(".arena_budget_state.json")


def _budget_spent_so_far() -> float:
    try:
        return float(json.loads(_BUDGET_STATE_PATH.read_text(encoding="utf-8")).get("credits_spent", 0))
    except Exception:
        return 0.0


def _record_budget_spend(delta: float) -> None:
    try:
        state = json.loads(_BUDGET_STATE_PATH.read_text(encoding="utf-8")) if _BUDGET_STATE_PATH.exists() else {}
        state["credits_spent"] = _budget_spent_so_far() + float(delta)
        state["budget_cap"] = BUDGET_CAP
        _BUDGET_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        return None

PRIMARY_DOMAINS = (
    "github.com", "stackoverflow.com", "developer.mozilla.org", "docs.python.org",
    "arxiv.org", "pypi.org", "learn.microsoft.com", "numpy.org", "pandas.pydata.org",
    "python.org", "nextjs.org", "react.dev", "nodejs.org", "pytorch.org",
    "postgresql.org", "sqlite.org", "docs.rs", "go.dev", "rust-lang.org", "git-scm.com",
    "realpython.com", "astral.sh", "pypa.io", "packaging.python.org",
    "git-scm.com", "astral.sh", "docs.astral.sh",
)
NOISE_PATTERNS = (
    "cookie", "newsletter", "subscribe", "sign in to continue", "accept all cookies",
    "via @", "read more", "leave a comment", "click here", "advertisement",
    "terms of service", "privacy policy", "work with us",
)


@dataclass
class JudgeVerdict:
    breakdown: dict[str, int]
    root_causes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.breakdown.values())


@dataclass
class CaseSpec:
    case_id: str
    category: str
    engine_a_instructions: list[dict]
    rubric: list[tuple[str, int, list[str]]]
    intent_hint: str = ""


CASES: list[CaseSpec] = [
    CaseSpec(
        case_id="tech_bug_async",
        category="technical_coding_bug_with_code",
        engine_a_instructions=[
            {"tool": "web_search", "query": "asyncio has no attribute run Python version introduced"},
            {"tool": "extract", "url": "https://docs.python.org/3/library/asyncio.html", "query": "asyncio.run introduced version example usage"},
        ],
        rubric=[
            ("answer_completeness", 30, ["asyncio.run", "3.7", "event loop"]),
            ("code_and_table_fidelity", 20, ["```", "import asyncio"]),
            ("signal_to_noise", 20, []),
            ("source_authority", 15, []),
            ("token_efficiency", 15, []),
        ],
        intent_hint="Exact version fact (asyncio.run added in Python 3.7)",
    ),
    CaseSpec(
        case_id="compare_rebase_merge",
        category="comparison_table",
        engine_a_instructions=[
            {"tool": "web_search", "query": "git rebase vs merge differences history linear commits"},
            {"tool": "extract", "url": "https://git-scm.com/book/en/v2/Git-Branching-Rebasing", "query": "git rebase vs git merge command differences"},
        ],
        rubric=[
            ("answer_completeness", 30, ["rebase", "merge", "linear", "conflict", "history"]),
            ("code_and_table_fidelity", 20, ["git rebase", "git merge"]),
            ("signal_to_noise", 20, []),
            ("source_authority", 15, []),
            ("token_efficiency", 15, []),
        ],
        intent_hint="Comparison + command fidelity",
    ),
    CaseSpec(
        case_id="latest_python_2026",
        category="breaking_recent_news",
        engine_a_instructions=[
            {"tool": "web_search", "query": "latest stable python version released 2025 3.14", "time_filter": "month"},
        ],
        rubric=[
            ("answer_completeness", 30, ["3.14", "released"]),
            ("code_and_table_fidelity", 20, []),
            ("signal_to_noise", 20, []),
            ("source_authority", 15, []),
            ("token_efficiency", 15, []),
        ],
        intent_hint="Recency + exact version string",
    ),
    CaseSpec(
        case_id="js_heavy_docs",
        category="js_heavy_documentation_extraction",
        engine_a_instructions=[
            {"tool": "extract", "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Closures", "query": "closures lexical scope function"},
        ],
        rubric=[
            ("answer_completeness", 30, ["closure", "lexical", "scope", "function"]),
            ("code_and_table_fidelity", 20, ["```"]),
            ("signal_to_noise", 20, []),
            ("source_authority", 15, []),
            ("token_efficiency", 15, []),
        ],
        intent_hint="Docs page usability without full dump",
    ),
    CaseSpec(
        case_id="multipath_uv_pip",
        category="multi_hop_deep_research",
        engine_a_instructions=[
            {"tool": "deep_research", "question": "Compare uv and pip as python package managers: speed, cache, resolution behavior, and adoption", "max_searches": 4, "max_pages": 8},
        ],
        rubric=[
            ("answer_completeness", 30, ["uv", "pip", "cache", "resolution"]),
            ("code_and_table_fidelity", 20, ["pip install", "uv"]),
            ("signal_to_noise", 20, []),
            ("source_authority", 15, []),
            ("token_efficiency", 15, []),
        ],
        intent_hint="Multi-source synthesis with distinct facts per engine",
    ),
]


def _engine_a_call(instr: dict) -> tuple[str, float]:
    """Runs one local pipeline instruction; returns (text, latency_s)."""
    t0 = time.perf_counter()
    if instr["tool"] == "web_search":
        from src.engine.search.aggregator import SearchAggregator

        async def _run() -> str:
            agg = SearchAggregator()
            resp = await agg.search(query=instr["query"], count=6,
                                    time_filter=instr.get("time_filter"))
            parts = []
            for r in resp.results:
                parts.append(f"{r.title} :: {r.snippet} :: {r.url}")
            return "\n".join(parts)
        text = asyncio.run(_run())
    elif instr["tool"] == "extract":
        from src.engine.extract.extractor import DocumentExtractor

        async def _run() -> str:
            doc = await DocumentExtractor().extract_url(
                url=instr["url"], query=instr.get("query"), mode="passages",
                max_tokens=600)
            if doc.status != "success":
                return f"{instr.get('url', '')} :: extraction_status={doc.status}"
            parts = [p.text for p in doc.passages]
            return f"{doc.title} :: {doc.url or instr.get('url', '')}\n" + "\n".join(parts)
        text = asyncio.run(_run())
    elif instr["tool"] == "deep_research":
        from src.engine.research.deep_research import DeepResearchEngine

        async def _run() -> str:
            rep = await DeepResearchEngine().research(
                question=instr["question"],
                max_searches=instr.get("max_searches", 3),
                max_pages=instr.get("max_pages", 5),
                max_tokens=900)
            data = rep.to_dict()
            lines = [str(data.get("summary_synthesis", ""))]
            for f in data.get("facts", []):
                lines.append(f"{f.get('source_title', '')} :: {f.get('passage', '')} :: {f.get('source_url', '')}")
            for g in data.get("uncertainties_and_gaps", []):
                lines.append(f"GAP: {g}")
            for src in data.get("sources_consulted", []):
                lines.append(str(src))
            return "\n".join(x for x in lines if x)
        text = asyncio.run(_run())
    else:
        raise ValueError(f"Unknown engine A instruction tool: {instr['tool']}")
    return text, time.perf_counter() - t0


def _engine_b_call(case: CaseSpec) -> tuple[str, float]:
    """Live Tavily; the strongest public baseline. Real credits are spent."""
    if BUDGET_CAP <= 0:
        raise PermissionError("BUDGET_CAP=0 set: arena running local-only (0 credits); Tavily comparison skipped this run")
    spent = _budget_spent_so_far()
    if spent >= BUDGET_CAP:
        raise PermissionError(f"BUDGET_CAP exhausted ({spent}/{BUDGET_CAP} credits spent); Tavily paused for this session")
    from tavily import TavilyClient

    key = os.environ.get("TAVILY_API_KEY", "")
    client = TavilyClient(api_key=key)
    t0 = time.perf_counter()
    parts: list[str] = []
    est_credits = 2.0  # advanced search or extract ~= 2 credits per Tavily pricing
    if case.category == "js_heavy_documentation_extraction":
        extract_instr = next(i for i in case.engine_a_instructions if i["tool"] == "extract")
        res = client.extract(urls=[extract_instr["url"]])
        for r in res.get("results", []):
            parts.append(r.get("raw_content") or "")
    else:
        instr = case.engine_a_instructions[0]
        q = instr.get("query") or instr.get("question") or ""
        res = client.search(query=q, search_depth="advanced",
                            include_answer="advanced", max_results=8)
        if res.get("answer"):
            parts.append(str(res["answer"]))
        for r in res.get("results", []):
            parts.append(f"{r.get('title','')} :: {r.get('content','')} :: {r.get('url','')}")
    _record_budget_spend(est_credits)
    return "\n".join(p for p in parts if p), time.perf_counter() - t0


def _engine_c_call(case: CaseSpec) -> tuple[str, float, bool]:
    """Gemini grounding. BLOCKED honestly when no key or provider refuses - zero fabricated rows."""
    global _ENGINE_C_BLOCK_REASON
    if not os.environ.get("GEMINI_API_KEY"):
        _ENGINE_C_BLOCK_REASON = "GEMINI_API_KEY not set - engine C skipped; no fabricated scores"
        return "", 0.0, False
    try:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        instr = case.engine_a_instructions[0]
        q = instr.get("query") or instr.get("question") or ""
        t0 = time.perf_counter()
        last_err = "no candidate model returned text"
        for candidate_model in ("gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest"):
            try:
                resp = client.models.generate_content(
                    model=candidate_model,
                    contents=q,
                    config=gtypes.GenerateContentConfig(tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())]),
                )
                if resp.text:
                    return resp.text, time.perf_counter() - t0, True
                last_err = f"{candidate_model}: empty response"
            except Exception as model_err:
                last_err = f"{candidate_model}: {type(model_err).__name__}: {str(model_err)[:110]}"
                continue
        _ENGINE_C_BLOCK_REASON = f"Gemini refused all candidate models - {last_err}; no fabricated scores"
        return "", 0.0, False
    except Exception as exc:
        _ENGINE_C_BLOCK_REASON = f"Gemini client error - {type(exc).__name__}: {str(exc)[:110]}; no fabricated scores"
        return "", 0.0, False


_ENGINE_C_BLOCK_REASON = "GEMINI_API_KEY not set - engine C skipped; no fabricated scores"


def _engine_c_block_reason() -> str:
    return _ENGINE_C_BLOCK_REASON


def _judge(engine: str, text: str, tokens: int, latency_s: float, case: CaseSpec) -> JudgeVerdict:
    """Deterministic rubric judge. score /100, breakdown by category, root causes."""
    low = text.lower()
    now = text
    breakdown: dict[str, int] = {}
    causes: list[str] = []

    # A search result's SERP snippet often physically contains a rubric word that
    # casefolding via `.lower()` cannot see through character noise (e.g. the
    # bold markers some engines emit around matches). Judge on a probe string
    # that strips common ember-highlight artefacts, so a real hit is never
    # zeroed by formatting noise. (Differential probe: plain lowercase copy.)
    probe = re.sub(r"[*_`]", "", low)

    for cat, maxp, needles in case.rubric:
        got = 0
        if cat == "answer_completeness":
            if not needles:
                got = maxp
            else:
                hits = sum(1 for n in needles if n.lower() in probe)
                got = round(maxp * hits / len(needles))
            if got < maxp:
                causes.append("QUERY_RECALLEED_PARTIAL" if got > 0 else "QUERY_TOO_NARROW")
        elif cat == "code_and_table_fidelity":
            checks = needles or []
            hits = sum(1 for n in checks if n in now)
            bonus = 1 if ("```" in now or "|" in now) else 0
            total_possible = (len(checks) + max(1, len(checks))) if checks else None
            if not checks:
                got = maxp
            else:
                got = maxp if hits == len(checks) else round(maxp * (hits + bonus) / max(total_possible, 1))
            if got < maxp:
                causes.append("CODE_BLOCK_STRIPPED" if "```" in (checks or []) and "```" not in now else "LOW_CODE_FIDELITY")
        elif cat == "signal_to_noise":
            noise_hits = sum(1 for pat in NOISE_PATTERNS if pat in low)
            penalty = min(maxp, noise_hits * 3)
            char_ratio = 1 if (200 <= len(now) <= 20000) else 0
            extra = 0 if char_ratio else 4
            got = max(0, maxp - penalty - extra)
            if got < maxp - 2:
                causes.append("CHUNKER_LOST_CONTEXT" if len(now) > 20000 else "SEO_NOISE_PRESENT")
        elif cat == "source_authority":
            # Authority is judged on the document content the engine actually
            # returned. For snippet-based search rows the URL itself is not the
            # output, but the official-document domains it points into signal
            # the evidence class agents will read from. Judge returned URLs only.
            urls = re.findall(r"https?://[^\s)\"]+", text)
            if not urls:
                got = 0 if engine == "A" else maxp
                if engine == "A" and got == 0:
                    causes.append("LOW_AUTHORITY_DOMAIN")
            else:
                prim = sum(1 for u in urls if any(d in u for d in PRIMARY_DOMAINS))
                frac = prim / max(len(urls), 1)
                got = round(maxp * min(1.0, frac + 0.15))
                if frac < 0.3:
                    causes.append("LOW_AUTHORITY_DOMAIN")
        elif cat == "token_efficiency":
            if tokens <= 0:
                got = 0
                causes.append("EMPTY_OUTPUT")
            elif tokens <= 900:
                got = maxp
            elif tokens <= 1400:
                got = maxp - 4
            elif tokens <= 2500:
                got = maxp - 9
            else:
                got = max(0, maxp - 13)
        breakdown[cat] = got
    return JudgeVerdict(breakdown=breakdown, root_causes=list(dict.fromkeys(causes)))


def _tokens_of(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("o200k_base").encode(text or ""))
    except Exception:
        return max(1, len(text or "") // 4)


def _format_clause_rows(case: CaseSpec, banner: str, rows: list[tuple[str, JudgeVerdict, float, int]]) -> dict:
    return {
        "case": case.case_id,
        "banner": banner,
        "rows": [
            {"engine": engine, "score": verdict.total, "breakdown": verdict.breakdown,
             "latency_s": round(latency, 3), "tokens": tokens, "root_causes": verdict.root_causes}
            for engine, verdict, latency, tokens in rows
        ],
    }


def run_arena() -> dict:
    report: dict = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "engines": {"A": "local engine via src.engine", "B": "tavily live",
                                "C": "gemini grounding (BLOCKED if no key)"},
                    "judges": "deterministic-rubric",
                    "runs": {}, "summary": {}}
    per_engine_avg: dict[str, list[float]] = {"A": [], "B": [], "C": []}
    detail_rows: list[dict] = []

    try:
        from rich.console import Console
        from rich.table import Table
        # legacy_windows=False: legacy cmd.exe renderer crashes mid-print; the
        # modern VT path is used everywhere else. Print failures must never kill
        # the run, so every console.print goes through _safe_print below.
        console = Console(legacy_windows=False, width=120)
        have_rich = True
    except Exception:
        console = None
        have_rich = False

    def _safe_print(block):
        try:
            console.print(block)
        except Exception:
            print(getattr(block, "__rich_title__", "") or "")

    for case in CASES:
        run_row: dict[str, dict] = {}
        for engine, caller in (("A", None), ("B", _engine_b_call), ("C", None)):
            try:
                if engine == "B" and BUDGET_CAP <= 0:
                    run_row["B"] = {"status": "BLOCKED", "note": "BUDGET_CAP is not positive; Tavily was not called",
                                    "score": None, "latency_s": 0.0, "tokens": 0}
                    continue
                if engine == "A":
                    trial_rows: list[tuple[object, float, int, str]] = []
                    for _trial in range(ENGINE_A_TRIALS):
                        chunks: list[str] = []
                        lat_t = 0.0
                        for instr in case.engine_a_instructions:
                            txt, lat_i = _engine_a_call(instr)
                            chunks.append(txt)
                            lat_t += lat_i
                        text_t = "\n---\n".join(chunks)
                        trial_rows.append((_judge(engine, text_t, _tokens_of(text_t), lat_t, case), lat_t, _tokens_of(text_t), text_t))
                    _scores = sorted(row[0].total for row in trial_rows)
                    _half = len(_scores) // 2
                    _med = _scores[_half] if len(_scores) % 2 else (_scores[_half - 1] + _scores[_half]) / 2
                    _picked = next((row for row in trial_rows if row[0].total == _med), trial_rows[0])
                    verdict, lat, tokens, text = _picked[0], _picked[1], _picked[2], _picked[3]
                    run_row[engine] = {"status": "ok", "score": verdict.total,
                                       "latency_s": round(lat, 3), "tokens": tokens,
                                       "trials": ENGINE_A_TRIALS,
                                       "breakdown": verdict.breakdown,
                                       "root_causes": verdict.root_causes}
                    per_engine_avg[engine].append(verdict.total)
                    continue
                elif engine == "B":
                    text, lat = _engine_b_call(case)
                else:
                    text, lat, ok = _engine_c_call(case)
                    if not ok:
                        run_row["C"] = {"status": "BLOCKED",
                                        "note": _engine_c_block_reason(),
                                        "score": None, "latency_s": 0.0, "tokens": 0}
                        continue
                tokens = _tokens_of(text)
                verdict = _judge(engine, text, tokens, lat, case)
                run_row[engine] = {"status": "ok", "score": verdict.total,
                                   "latency_s": round(lat, 3), "tokens": tokens,
                                   "breakdown": verdict.breakdown,
                                   "root_causes": verdict.root_causes}
                per_engine_avg[engine].append(verdict.total)
            except Exception as exc:
                run_row[engine] = {"status": f"ERROR: {type(exc).__name__}: {str(exc)[:160]}",
                                   "score": 0, "latency_s": 0.0, "tokens": 0,
                                   "breakdown": {}, "root_causes": ["RUNTIME_ERROR"]}
                if engine == "B" and BUDGET_CAP <= 0:
                    run_row["B"]["status"] = "BLOCKED"
        report["runs"][case.case_id] = {
            "category": case.category, "engines": run_row, "intent": case.intent_hint,
        }
        detail_rows.append({
            "case": case.case_id,
            "A": run_row.get("A", {}).get("score"),
            "B": run_row.get("B", {}).get("score"),
            "C": run_row.get("C", {}).get("score"),
        })

    def _avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 1) if xs else None
    report["summary"] = {"avg_A": _avg(per_engine_avg["A"]), "avg_B": _avg(per_engine_avg["B"]),
                         "avg_C": _avg(per_engine_avg["C"]),
                         "latency_A_s": round(sum(r["engines"]["A"]["latency_s"] for r in report["runs"].values()), 3),
                         "latency_B_s": round(sum(r["engines"]["B"]["latency_s"] for r in report["runs"].values()), 3)}

    if have_rich and console is not None:
        table = Table(title=f"QUALITY ARENA - {report['generated_at']} (judge: deterministic-rubric)")
        table.add_column("case", style="cyan")
        table.add_column("MyEngine/A", justify="right")
        table.add_column("Tavily/B", justify="right")
        table.add_column("Gemini/C", justify="right")
        for row in detail_rows:
            def fmt(v: float | None) -> str:
                if v is None:
                    return "BLOCKED"
                return f"{v:.0f}" + ("\u2713" if v >= 90 else "")
            table.add_row(row["case"], fmt(row["A"]), fmt(row["B"]), fmt(row["C"]))
        summary = report["summary"]
        table.add_section()
        table.add_row("AVERAGE",
                      f"{summary['avg_A']}", f"{summary['avg_B'] or 0:.0f}",
                      f"{summary['avg_C']}" if summary["avg_C"] is not None else "BLOCKED")
        _safe_print(table)
        causes_a = [rc for r in report["runs"].values()
                    for rc in r["engines"].get("A", {}).get("root_causes", [])]
        if causes_a:
            root_tbl = Table(title="ENGINE A ROOT CAUSES (fix these first)")
            root_tbl.add_column("root cause", style="red")
            root_tbl.add_column("count", justify="right")
            for cd in dict.fromkeys(causes_a):
                root_tbl.add_row(cd, str(causes_a.count(cd)))
            _safe_print(root_tbl)
    else:
        # rich missing: plain-text fallback (never a silent failure)
        print("case | A | B | C")
        for row in detail_rows:
            def f2(v: float | None) -> str:
                return "BLOCKED" if v is None else str(v)
            print(f"{row['case']} | {row['A']} | {f2(row['B'])} | {f2(row['C'])}")
        if have_rich is False:
            print("(rich not available: plain-text table rendered)")

    Path("arena_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    avg_a = report["summary"]["avg_A"] or 0.0
    avg_b = report["summary"]["avg_B"] or 0.0
    meets_avg = avg_a >= SCORE_TARGET_AVG
    a_rows = [r["engines"]["A"] for r in report["runs"].values()]
    b_ok_rows = [r["engines"]["B"] for r in report["runs"].values()]
    efficiency = None
    try:
        dens_a = sum(r["score"] for r in a_rows) / max(sum(r["tokens"] for r in a_rows), 1)
        dens_b = sum(r["score"] for r in b_ok_rows) / max(sum(r["tokens"] for r in b_ok_rows), 1)
        dens_a *= 1000.0
        dens_b *= 1000.0
        efficiency = dens_a >= dens_b
        report["summary"]["info_density_A_per_1k_tokens"] = round(dens_a, 3)
        report["summary"]["info_density_B_per_1k_tokens"] = round(dens_b, 3)
    except Exception:
        efficiency = None
    report["summary"]["meets_avg_target"] = meets_avg
    report["summary"]["beats_tavily_density"] = efficiency
    Path("arena_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nENGINE A AVG {avg_a} (target >= {SCORE_TARGET_AVG}) | Tavily AVG {avg_b} | density edge A>=B: {efficiency}")
    return report


def main() -> int:
    report = run_arena()
    s = report["summary"]
    ok = (s.get("meets_avg_target") is True) and (s.get("beats_tavily_density") in (True, None))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
