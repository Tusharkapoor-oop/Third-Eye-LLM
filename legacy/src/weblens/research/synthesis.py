"""Deterministic hypothesis testing and contradiction resolution.

This layer does not call an LLM and does not invent prose. It turns a research
outcome into a claim ledger, tests explicit hypotheses with lexical stance
rules, resolves contradictions using source tier, recency and independent
domain support, and assembles an answer only from verbatim claims.

The stance classifier is heuristic. A ``supported`` verdict means the collected
evidence is consistent with the hypothesis, not that the hypothesis is proven.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from ..errors import resolve_budget
from ..extract.passages import tokenize
from ..lexical import STOPWORDS, query_terms
from ..search.router import clean_query
from ..tokens import count_json_tokens
from ..urls import registrable_domain
from .engine import (
    FRESH,
    GAP_IGNORE,
    NUM,
    UNIT_NORM,
    Finding,
    ResearchEngine,
    ResearchOutcome,
    detect_conflicts,
)

Verdict = Literal["supported", "refuted", "conflicting", "insufficient"]
Stance = Literal["supports", "refutes", "neutral"]
HypothesisKind = Literal["polar", "definition", "comparison", "numeric"]
Polarity = Literal["affirmative", "negative"]

_POLAR_START = re.compile(
    r"^\s*(?:is|are|was|were|does|do|did|can|could|will|would|should|has|have|had|must|may|might)\b",
    re.I,
)
_COMPARE = re.compile(
    r"^\s*(?:compare\s+)?(.+?)\s+(?:vs\.?|versus)\s+(.+?)"
    r"(?:\s+(?:for|in|on|with|when)\s+(.+))?[?.!]*$",
    re.I,
)
_COMPARE_SUFFIX = re.compile(r"^\s*(.+?)\s+and\s+(.+?)\s+comparison\s*$", re.I)
_COMPARE_AND = re.compile(r"^\s*compare\s+(.+?)\s+and\s+(.+?)[?.!]*$", re.I)
_DIFF = re.compile(
    r"\bdifferences?\s+between\s+(.+?)\s+and\s+(.+?)"
    r"(?:\s+(?:for|in|on|with|when)\s+(.+))?[?.!]*$",
    re.I,
)
_NUMERIC_INTENT = re.compile(
    r"\b(?:price|cost|how much|how many|how long|latency|time|timeout|size|memory|percentage|percent|"
    r"rate|speed|fast|throughput|capacity|limit|maximum|minimum|default|population|"
    r"distance|height|weight|temperature|age|duration)\b",
    re.I,
)

# Words that describe the *shape* of a numeric question but not its subject.
# "maximum SQLite database size" must not be answered by a page that only
# shares "maximum" and "size" (for example a WhatsApp group-size paragraph).
_NUMERIC_GENERIC = frozenset(
    {
        "maximum",
        "minimum",
        "max",
        "min",
        "size",
        "value",
        "number",
        "many",
        "much",
        "how",
        "price",
        "cost",
        "rate",
        "speed",
        "time",
        "latency",
        "throughput",
        "percentage",
        "percent",
        "default",
        "limit",
        "fast",
        "long",
        "have",
        "has",
        "had",
        "does",
        "do",
        "did",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
    }
)

_PRIMARY_SUFFIXES = (".gov", ".edu", ".mil", ".int")
_PRIMARY_HOSTS = {
    "arxiv.org",
    "rfc-editor.org",
    "w3.org",
    "ietf.org",
    "iso.org",
    "nist.gov",
    "europa.eu",
    "who.int",
    "python.org",
    "developer.mozilla.org",
    "github.com",
    "learn.microsoft.com",
    "cloud.google.com",
    "aws.amazon.com",
    "postgresql.org",
    "mysql.com",
    "sqlite.org",
    "openai.com",
    "anthropic.com",
}
_SECONDARY_HOSTS = {
    "wikipedia.org",
    "britannica.com",
    "investopedia.com",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "nytimes.com",
    "theguardian.com",
    "arstechnica.com",
    "techcrunch.com",
    "theverge.com",
    "wired.com",
    "stackoverflow.com",
    "stackexchange.com",
}
_SOCIAL_HOSTS = {
    "twitter.com",
    "x.com",
    "reddit.com",
    "facebook.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
}
_TIER_WEIGHTS = {"primary": 1.0, "secondary": 0.6, "unknown": 0.45, "social": 0.25}

_NEGATION = re.compile(
    r"\b(?:not|no|never|none|cannot|without|lacks?|fails?|failed|unable|absent|"
    r"unrelated|neither|nor|hardly|rarely|unlikely)\b",
    re.I,
)
_ABSENCE = re.compile(
    r"\b(?:no|not enough|insufficient|little|limited)\s+(?:evidence|data|studies|research|proof)\b"
    r"|\b(?:unknown|not found|none found)\b",
    re.I,
)
_UNCERTAINTY = re.compile(
    r"\b(?:may|might|could|possibly|perhaps|suggests?|suggested|appears?|appeared|"
    r"seems?|seemed|unclear|uncertain|debat(?:e|ed|able)|mixed|inconclusive|"
    r"preliminary|reportedly|allegedly)\b",
    re.I,
)
_NOT_CLEAR = re.compile(r"\bnot necessarily\b|\bnot clear\b|\bunclear\b", re.I)
_PREDICATE_RE = re.compile(
    r"\b(?:is|are|was|were|has|have|had|does|do|did|can|could|will|would|should|"
    r"causes?|caused|increases?|decreases?|reduces?|improves?|supports?|allows?|"
    r"provides?|enables?|requires?|uses?|returns?|creates?|prevents?|leads? to|"
    r"results? in|means?|refers? to|states?|defines?|describes?)\b",
    re.I,
)

_PREDICATE_TERMS = {
    "cause",
    "causes",
    "caused",
    "increase",
    "increases",
    "increased",
    "decrease",
    "decreases",
    "decreased",
    "reduce",
    "reduces",
    "reduced",
    "improve",
    "improves",
    "improved",
    "cancel",
    "cancels",
    "cancelled",
    "remove",
    "removes",
    "removed",
    "support",
    "supports",
    "supported",
    "allow",
    "allows",
    "enable",
    "enables",
    "provide",
    "provides",
    "require",
    "requires",
    "use",
    "uses",
    "used",
    "return",
    "returns",
    "create",
    "creates",
    "prevent",
    "prevents",
    "lead",
    "leads",
    "result",
    "results",
    "mean",
    "means",
    "refer",
    "refers",
    "work",
    "works",
    "happen",
    "happens",
    "exist",
    "exists",
    "change",
    "changes",
    "become",
    "becomes",
    "contain",
    "contains",
    "include",
    "includes",
    "affect",
    "affects",
    "help",
    "helps",
    "make",
    "makes",
    "faster",
    "slower",
    "higher",
    "lower",
    "better",
    "worse",
    "larger",
    "smaller",
    "more",
    "less",
    "true",
    "false",
    "correct",
    "safe",
    "legal",
    "available",
    "possible",
    "required",
    "allowed",
    "default",
    "maximum",
    "minimum",
    "fast",
}
_POSITIVE_CUES = {
    "supports",
    "support",
    "supported",
    "confirms",
    "confirm",
    "confirmed",
    "shows",
    "show",
    "demonstrates",
    "demonstrate",
    "proves",
    "prove",
    "causes",
    "cause",
    "caused",
    "allows",
    "allow",
    "enables",
    "enable",
    "provides",
    "provide",
    "returns",
    "return",
    "creates",
    "create",
    "found",
    "outperforms",
    "outperform",
    "outperformed",
    "exceeds",
    "exceed",
    "superior",
    "yes",
    "true",
    "correct",
}
_NEGATIVE_CUES = {
    "prevents",
    "prevent",
    "blocks",
    "block",
    "inhibits",
    "inhibit",
    "fails",
    "fail",
    "failed",
    "lacks",
    "lack",
    "cannot",
    "unable",
    "false",
    "incorrect",
    "underperforms",
    "underperform",
}
_OPPOSITE = {
    "faster": {"slower"},
    "slower": {"faster"},
    "higher": {"lower"},
    "lower": {"higher"},
    "more": {"less", "fewer"},
    "less": {"more"},
    "increase": {"decrease", "decreases", "reduce", "reduces"},
    "increases": {"decreases", "decrease", "reduces", "reduce"},
    "decrease": {"increase", "increases", "raise", "raises"},
    "decreases": {"increases", "increase", "raises", "raise"},
    "improve": {"worsen", "worsens", "degrade", "degrades"},
    "improves": {"worsens", "worsen", "degrades", "degrade"},
    "better": {"worse"},
    "worse": {"better"},
    "larger": {"smaller"},
    "smaller": {"larger"},
    "bigger": {"smaller"},
    "above": {"below"},
    "below": {"above"},
    "before": {"after"},
    "after": {"before"},
}


@dataclass(frozen=True)
class Hypothesis:
    id: str
    statement: str
    kind: HypothesisKind
    terms: tuple[str, ...]
    polarity: Polarity = "affirmative"
    entity: str | None = None


@dataclass
class Claim:
    id: str
    finding: Finding
    domain: str
    tier: str
    quality: float
    published_date: date | None = None


@dataclass
class Assessment:
    claim_id: str
    hypothesis_id: str
    stance: Stance
    strength: float
    cues: list[str] = field(default_factory=list)


@dataclass
class Resolution:
    topic: str
    winner: str
    reason: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)


@dataclass
class HypothesisResult:
    hypothesis: Hypothesis
    verdict: Verdict
    support: float
    confidence: float
    reason: str
    supporting: list[str] = field(default_factory=list)
    refuting: list[str] = field(default_factory=list)
    resolution: Resolution | None = None


@dataclass
class SynthesisOutcome:
    status: str
    query: str
    hypotheses: list[HypothesisResult]
    claims: list[Claim]
    assessments: list[Assessment]
    resolutions: list[Resolution]
    gaps: list[str]
    warnings: list[str]
    hops: list[dict]
    elapsed_ms: int
    tokens: int = 0
    budget: int = 8000
    searched: list[str] = field(default_factory=list)
    answer: str = ""

    def payload(self) -> dict:
        body = self._full_payload()
        target = max(120, self.budget - 6)
        if count_json_tokens(body) > target:
            body = self._trim(body, target)
        body["tok"] = count_json_tokens({**body, "tok": 0})
        if body["tok"] > self.budget:
            body["warn"] = list(dict.fromkeys([*(body.get("warn") or []), "budget_exhausted"]))
        self.tokens = int(body["tok"])
        return body

    def _full_payload(self) -> dict:
        by_id = {c.id: c for c in self.claims}
        hyp_payload = []
        for r in _ordered_results(self.hypotheses):
            item: dict = {
                "id": r.hypothesis.id,
                "s": r.hypothesis.statement,
                "kind": r.hypothesis.kind,
                "pol": r.hypothesis.polarity,
                "verdict": r.verdict,
                "sup": r.support,
                "conf": r.confidence,
                "why": r.reason,
            }
            if r.hypothesis.entity:
                item["ent"] = r.hypothesis.entity
            if r.supporting:
                item["yes"] = r.supporting
            if r.refuting:
                item["no"] = r.refuting
            if r.resolution:
                item["res"] = _resolution_payload(r.resolution)
            hyp_payload.append(item)
        claim_payload = []
        for c in self.claims:
            f = c.finding
            item = {
                "id": c.id,
                "c": f.claim,
                "u": f.url,
                "at": f.fetched_at,
                "s": f.span,
                "tier": c.tier,
                "q": c.quality,
            }
            if f.published:
                item["d"] = f.published
            if f.heading:
                item["h"] = f.heading
            claim_payload.append(item)
        body: dict = {
            "status": self.status,
            "q": self.query,
            "n": len(claim_payload),
            "hyp": hyp_payload,
            "claims": claim_payload,
            "support": _support_stats(self.claims, self.assessments, self.hypotheses),
            "gaps": self.gaps,
            "answer": self.answer,
            "ms": self.elapsed_ms,
            "tok": 0,
        }
        if self.resolutions:
            body["res"] = [_resolution_payload(r) for r in self.resolutions]
        if self.hops:
            body["hops"] = self.hops
        if self.searched:
            body["searched"] = list(dict.fromkeys(self.searched))[:8]
        if self.warnings:
            body["warn"] = list(dict.fromkeys(self.warnings))
        # Keep the ledger honest if a claim id is not in the list (defensive).
        for item in hyp_payload:
            yes = [x for x in item.get("yes", []) if x in by_id]
            no = [x for x in item.get("no", []) if x in by_id]
            if yes:
                item["yes"] = yes
            else:
                item.pop("yes", None)
            if no:
                item["no"] = no
            else:
                item.pop("no", None)
        return body

    def _trim(self, body: dict, target: int) -> dict:
        for key in ("hops", "searched", "answer"):
            if key in body:
                body.pop(key)
                if count_json_tokens(body) <= target:
                    return body
        if count_json_tokens(body) > target and body.get("claims"):
            referenced: set[str] = set()
            for h in body.get("hyp", []):
                referenced.update(h.get("yes", []))
                referenced.update(h.get("no", []))
            for r in body.get("res", []):
                referenced.update(r.get("ev", []))
            kept = [c for c in body["claims"] if c["id"] in referenced]
            if kept:
                body["claims"] = kept
            while count_json_tokens(body) > target and body.get("claims"):
                cid = body["claims"].pop()["id"]
                for h in body.get("hyp", []):
                    h["yes"] = [x for x in h.get("yes", []) if x != cid]
                    h["no"] = [x for x in h.get("no", []) if x != cid]
                for r in body.get("res", []):
                    r["ev"] = [x for x in r.get("ev", []) if x != cid]
            body["n"] = len(body.get("claims", []))
        if count_json_tokens(body) > target:
            body.pop("res", None)
        if count_json_tokens(body) > target:
            body["hyp"] = [
                {k: v for k, v in h.items() if k in {"id", "s", "kind", "pol", "verdict", "sup", "conf", "why", "ent"}}
                for h in body.get("hyp", [])
            ]
        while count_json_tokens(body) > target and body.get("hyp"):
            body["hyp"].pop()
        if count_json_tokens(body) > target:
            body = {
                "status": self.status,
                "q": self.query[:200],
                "n": len(self.claims),
                "support": body.get("support", {}),
                "gaps": body.get("gaps", [])[:4],
                "ms": self.elapsed_ms,
                "tok": 0,
                "warn": list(dict.fromkeys([*(body.get("warn") or []), "budget_exhausted"])),
            }
        return body


def _resolution_payload(r: Resolution) -> dict:
    item = {
        "topic": r.topic,
        "win": r.winner,
        "why": r.reason,
        "conf": r.confidence,
    }
    if r.evidence:
        item["ev"] = r.evidence
    if r.alternatives:
        item["alt"] = r.alternatives
    return item


# -- stable ids and source quality -----------------------------------------


def _hyp_id(kind: str, label: str, statement: str) -> str:
    raw = f"{kind}|{label}|{statement.lower()}"
    return "h" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


def _claim_id(finding: Finding) -> str:
    span = finding.span if isinstance(finding.span, list) and len(finding.span) == 2 else [0, len(finding.claim)]
    raw = f"{finding.url}|{span[0]}:{span[1]}|{finding.claim[:160]}"
    return "c" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


def _finding_key(f: Finding) -> tuple:
    norm = re.sub(r"\W+", " ", (f.claim or "").lower()).strip()[:160]
    return (f.url or "", tuple(f.span or []), norm)


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def source_tier(url: str) -> str:
    host = _host(url)
    if not host:
        return "unknown"
    if host.endswith(_PRIMARY_SUFFIXES):
        return "primary"
    if host in _PRIMARY_HOSTS or any(host.endswith("." + h) for h in _PRIMARY_HOSTS):
        return "primary"
    if host.startswith(("docs.", "developer.", "documentation.", "api.")):
        return "primary"
    if host in _SECONDARY_HOSTS or any(host.endswith("." + h) for h in _SECONDARY_HOSTS):
        return "secondary"
    if host.startswith("news."):
        return "secondary"
    if host in _SOCIAL_HOSTS or any(host.endswith("." + h) for h in _SOCIAL_HOSTS):
        return "social"
    return "unknown"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _recency(value: str | None) -> float:
    parsed = _parse_date(value)
    if parsed is None:
        return 0.0
    days = (date.today() - parsed).days
    if days < 0:
        return 0.0
    if days <= 365:
        return 0.2
    if days <= 1095:
        return 0.1
    return 0.0


def _domain(url: str) -> str:
    host = _host(url)
    return registrable_domain(host) if host else ""


def _variants(token: str) -> set[str]:
    t = token.lower()
    out = {t}
    if len(t) > 3 and t.endswith("s"):
        out.add(t[:-1])
    if len(t) > 4 and t.endswith("es"):
        out.add(t[:-2])
    if len(t) > 4 and t.endswith("ed"):
        out.add(t[:-2])
        out.add(t[:-1])
    if len(t) > 5 and t.endswith("ing"):
        out.add(t[:-3])
        out.add(t[:-3] + "e")
    if len(t) > 3 and t.endswith("e"):
        out.add(t[:-1])
    return out


def _match_terms(hyp_terms: tuple[str, ...], claim_tokens: set[str]) -> list[str]:
    claim_variants: set[str] = set()
    for t in claim_tokens:
        claim_variants |= _variants(t)
    return [t for t in hyp_terms if _variants(t) & claim_variants]


def _overlap(hyp_terms: tuple[str, ...], claim_tokens: set[str]) -> tuple[float, list[str]]:
    if not hyp_terms:
        return 0.0, []
    matched = _match_terms(hyp_terms, claim_tokens)
    return len(matched) / len(hyp_terms), matched


def _normalize_text(text: str) -> str:
    t = (text or "").lower().replace("\u2019", "'")
    t = re.sub(r"\bcan't\b", "cannot", t)
    t = re.sub(r"\bwon't\b", "will not", t)
    t = re.sub(r"n't\b", " not", t)
    t = re.sub(r"\bnot only\b", "only", t)
    t = re.sub(r"\bno doubt\b", "doubt", t)
    return t


def _dedupe(items: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return tuple(out)


def _terms(text: str) -> list[str]:
    terms, _ = query_terms(text)
    return terms


def _build_claims(findings: list[Finding]) -> list[Claim]:
    claims: list[Claim] = []
    seen: set[tuple] = set()
    for f in findings:
        key = _finding_key(f)
        if key in seen:
            continue
        seen.add(key)
        url = f.url or ""
        tier = source_tier(url)
        claims.append(
            Claim(
                id=_claim_id(f),
                finding=f,
                domain=_domain(url),
                tier=tier,
                quality=round(_TIER_WEIGHTS[tier] + _recency(f.published), 3),
                published_date=_parse_date(f.published),
            )
        )
    return claims


# -- hypothesis generation -------------------------------------------------


def _comparison_parts(match: re.Match) -> tuple[str, str, str]:
    groups = match.groups()
    left = (groups[0] or "").strip(" ,;:?!.")
    right = (groups[1] or "").strip(" ,;:?!.")
    qualifier = ""
    if len(groups) >= 3 and groups[2]:
        qualifier = groups[2].strip(" ,;:?!.")
    prefix_terms = [t for t in _terms(match.string[: match.start()]) if t not in {"difference", "comparison"}]
    if prefix_terms:
        qualifier = " ".join([qualifier, *prefix_terms]).strip()
    return left, right, qualifier


def generate_hypotheses(query: str) -> list[Hypothesis]:
    q = " ".join((query or "").strip().split())
    if not q:
        return []
    q_no_punct = q.rstrip(" ?!.")
    low = q_no_punct.lower()

    match = _COMPARE.search(q_no_punct) or _DIFF.search(q_no_punct)
    if match is None:
        match = _COMPARE_AND.search(q_no_punct)
    if match is None:
        match = _COMPARE_SUFFIX.search(q_no_punct)
    if match:
        left, right, qualifier = _comparison_parts(match)
        property_terms = _dedupe(_terms(qualifier)) if qualifier else []
        out: list[Hypothesis] = []
        for ent in _dedupe([left, right]):
            ent = ent.strip(" ,;:?!.")
            if not ent or len(ent) > 80:
                continue
            terms = _dedupe([*_terms(ent), *property_terms])
            if not terms:
                continue
            statement = f"{ent} is described by the evidence"
            if qualifier:
                statement += f" for: {qualifier}"
            out.append(
                Hypothesis(
                    id=_hyp_id("comparison", ent.lower(), statement),
                    statement=statement,
                    kind="comparison",
                    terms=terms,
                    entity=ent,
                )
            )
        direct_terms = _dedupe(_terms(q_no_punct)) or tuple(property_terms)
        if direct_terms:
            out.append(
                Hypothesis(
                    id=_hyp_id("definition", "direct", q_no_punct),
                    statement=f"The evidence addresses: {q_no_punct}",
                    kind="definition",
                    terms=direct_terms,
                )
            )
        return out

    if _POLAR_START.match(q_no_punct):
        terms = _dedupe(_terms(q_no_punct))
        if not terms:
            return []
        asked_negated = bool(_NEGATION.search(_normalize_text(q_no_punct)))
        first: Polarity = "negative" if asked_negated else "affirmative"
        second: Polarity = "affirmative" if asked_negated else "negative"
        return [
            Hypothesis(
                id=_hyp_id("polar", first, q_no_punct),
                statement=q_no_punct,
                kind="polar",
                terms=terms,
                polarity=first,
            ),
            Hypothesis(
                id=_hyp_id("polar", second, f"Not ({q_no_punct})"),
                statement=f"Not ({q_no_punct})",
                kind="polar",
                terms=terms,
                polarity=second,
            ),
        ]

    if _NUMERIC_INTENT.search(low):
        terms = _dedupe(_terms(q_no_punct))
        if terms:
            return [
                Hypothesis(
                    id=_hyp_id("numeric", "numeric", q_no_punct),
                    statement=q_no_punct,
                    kind="numeric",
                    terms=terms,
                )
            ]

    terms = _dedupe(_terms(q_no_punct))
    if not terms:
        return []
    return [
        Hypothesis(
            id=_hyp_id("definition", "definition", q_no_punct),
            statement=q_no_punct,
            kind="definition",
            terms=terms,
        )
    ]


# -- stance classification -------------------------------------------------


def _cue_tokens(tokens: set[str]) -> set[str]:
    out: set[str] = set()
    for token in tokens:
        out |= _variants(token)
    return out


def _opposite_cue(hyp_terms: tuple[str, ...], tokens: set[str]) -> str | None:
    present = _cue_tokens(tokens)
    for term in hyp_terms:
        variants = _variants(term)
        # A claim that states the same direction and also mentions an opposite
        # word is usually talking about another object ("increases alertness
        # and reduces fatigue"), not contradicting the hypothesis.
        if variants & present:
            continue
        for variant in variants:
            if variant in _OPPOSITE and (_OPPOSITE[variant] & present):
                return variant
    return None


def _negation_relevant(text: str, hyp_terms: tuple[str, ...]) -> bool:
    """Return True when a negation is plausibly attached to the predicate.

    Research claims can contain code examples or quoted comments with an
    unrelated "not" ("# We do not know the timeout when starting"). Treating
    every negation as a refutation makes the claim contradict a hypothesis it
    never addresses. Require the negation to appear before a predicate term
    from the question, within a bounded window.
    """

    predicate_terms = [t for t in hyp_terms if t in _PREDICATE_TERMS]
    if not predicate_terms:
        return True
    positions = [
        match.start()
        for term in predicate_terms
        for variant in _variants(term)
        for match in re.finditer(rf"\b{re.escape(variant)}", text)
    ]
    if not positions:
        return False
    return any(0 <= pos - negation.start() <= 100 for negation in _NEGATION.finditer(text) for pos in positions)


def _neutral(claim_id: str, hyp_id: str, cue: str) -> Assessment:
    return Assessment(claim_id, hyp_id, "neutral", 0.0, [cue])


def assess_claim(claim: Claim, hyp: Hypothesis) -> Assessment:
    tokens = set(tokenize(claim.finding.claim))
    overlap, matched = _overlap(hyp.terms, tokens)
    if hyp.kind == "numeric":
        if overlap < 0.34 or not NUM.search(claim.finding.claim):
            return _neutral(claim.id, hyp.id, "numeric_mismatch")
        return _neutral(claim.id, hyp.id, "numeric_hypothesis")
    if hyp.kind == "comparison" and hyp.entity:
        entity_terms = set(_terms(hyp.entity))
        if entity_terms and not (entity_terms & set(matched)):
            return _neutral(claim.id, hyp.id, "entity_not_matched")

    text = _normalize_text(claim.finding.claim)
    if hyp.kind in {"definition", "comparison"}:
        if overlap < 0.5:
            return _neutral(claim.id, hyp.id, "no_term_overlap")
        if _ABSENCE.search(text):
            return _neutral(claim.id, hyp.id, "absence_of_evidence")
        if _NOT_CLEAR.search(text) or _UNCERTAINTY.search(text):
            return _neutral(claim.id, hyp.id, "uncertain_evidence")
        strength = 0.35 + 0.45 * overlap
        if _PREDICATE_RE.search(text):
            strength += 0.1
        if re.search(r"\d", text):
            strength += 0.05
        return Assessment(
            claim.id,
            hyp.id,
            "supports",
            round(min(0.95, strength), 3),
            ["descriptive_match"],
        )

    if overlap < 0.34:
        return _neutral(claim.id, hyp.id, "no_term_overlap")
    if _ABSENCE.search(text):
        return _neutral(claim.id, hyp.id, "absence_of_evidence")
    if _NOT_CLEAR.search(text):
        return _neutral(claim.id, hyp.id, "not_clear")

    negated = bool(_NEGATION.search(text)) and _negation_relevant(text, hyp.terms)
    uncertain = bool(_UNCERTAINTY.search(text))
    opposite = _opposite_cue(hyp.terms, tokens)
    predicate_terms = [t for t in hyp.terms if t in _PREDICATE_TERMS]
    predicate_matched = bool(predicate_terms) and any(t in matched for t in predicate_terms)
    cue_variants = _cue_tokens(tokens)
    positive = bool(cue_variants & _POSITIVE_CUES)
    negative = bool(cue_variants & _NEGATIVE_CUES)

    if negated:
        stance: Stance = "refutes" if hyp.polarity == "affirmative" else "supports"
        strength = 0.5 + 0.35 * overlap
        if uncertain:
            strength -= 0.1
        return Assessment(
            claim.id,
            hyp.id,
            stance,
            round(max(0.2, min(0.9, strength)), 3),
            ["negation"],
        )
    if uncertain:
        return _neutral(claim.id, hyp.id, "uncertain_evidence")
    if opposite:
        stance = "refutes" if hyp.polarity == "affirmative" else "supports"
        return Assessment(
            claim.id,
            hyp.id,
            stance,
            round(min(0.9, 0.6 + 0.2 * overlap), 3),
            ["directional_opposition"],
        )
    if predicate_matched:
        stance = "supports" if hyp.polarity == "affirmative" else "refutes"
        strength = 0.35 + 0.4 * overlap + 0.1
        if positive:
            strength += 0.05
        return Assessment(
            claim.id,
            hyp.id,
            stance,
            round(min(0.95, strength), 3),
            ["predicate_match"],
        )
    if positive and not negative:
        stance = "supports" if hyp.polarity == "affirmative" else "refutes"
        return Assessment(
            claim.id,
            hyp.id,
            stance,
            round(min(0.9, 0.4 + 0.35 * overlap), 3),
            ["positive_cue"],
        )
    if negative and not positive:
        stance = "refutes" if hyp.polarity == "affirmative" else "supports"
        return Assessment(
            claim.id,
            hyp.id,
            stance,
            round(min(0.9, 0.4 + 0.35 * overlap), 3),
            ["negative_cue"],
        )
    return _neutral(claim.id, hyp.id, "no_polarity_cue")


# -- numeric claims and resolution -----------------------------------------


@dataclass(frozen=True)
class _NumObs:
    unit: str
    value: float
    subject: frozenset[str]
    claim: Claim
    raw: str


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def _numeric_anchors(hyp: Hypothesis) -> frozenset[str]:
    """Topic terms that must appear in a numeric claim.

    Generic intent words such as "maximum" and "size" are deliberately excluded:
    they occur in almost every numeric sentence and cannot establish that the
    claim is about the requested subject.
    """

    return frozenset(t for t in hyp.terms if len(t) > 2 and t not in STOPWORDS and t not in _NUMERIC_GENERIC)


def _numeric_observations(claims: list[Claim], hyp: Hypothesis) -> list[_NumObs]:
    observations: list[_NumObs] = []
    fallback = frozenset(t for t in hyp.terms if len(t) > 2)
    anchors = _numeric_anchors(hyp)
    for claim in claims:
        text = claim.finding.claim
        if not NUM.search(text):
            continue
        tokens = set(tokenize(text))
        if anchors:
            # A claim that only shares "maximum"/"size" with the question is
            # not evidence for this subject. Accept the topic when it appears
            # in the claim, its heading, or its URL (for example sqlite.org).
            context = tokens | set(tokenize(claim.finding.heading or "")) | set(tokenize(claim.finding.url or ""))
            if not _match_terms(tuple(anchors), context):
                continue
        overlap, _ = _overlap(hyp.terms, tokens)
        if overlap < 0.34:
            continue
        for match in NUM.finditer(text):
            unit = UNIT_NORM.get(match.group("unit").lower(), match.group("unit").lower())
            try:
                value = float(match.group("num").replace(",", ""))
            except ValueError:
                continue
            if unit == "s":
                value *= 1000.0
                unit = "ms"
            before = text[max(0, match.start() - 140) : match.start()]
            subject = frozenset(
                t
                for t in tokenize(before)[-10:]
                if len(t) > 2
                and t not in STOPWORDS
                and t not in {"benchmark", "test", "study", "report", "average", "about", "approximately"}
            )
            observations.append(
                _NumObs(
                    unit=unit,
                    value=value,
                    subject=subject or fallback,
                    claim=claim,
                    raw=match.group(0),
                )
            )
    return observations


def _cluster_numeric(observations: list[_NumObs]) -> list[list[_NumObs]]:
    groups: list[list[_NumObs]] = []
    used: set[int] = set()
    for i, obs in enumerate(observations):
        if i in used:
            continue
        group = [obs]
        used.add(i)
        changed = True
        while changed:
            changed = False
            for j, other in enumerate(observations):
                if j in used or other.unit != obs.unit:
                    continue
                if any(_jaccard(item.subject, other.subject) >= 0.5 for item in group):
                    group.append(other)
                    used.add(j)
                    changed = True
        groups.append(group)
    return groups


def _side_stats(
    assessments: list[Assessment], claim_by_id: dict[str, Claim]
) -> tuple[float, set[str], set[str], date | None]:
    total = 0.0
    domains: set[str] = set()
    tiers: set[str] = set()
    newest: date | None = None
    for a in assessments:
        claim = claim_by_id.get(a.claim_id)
        if claim is None:
            continue
        total += a.strength * claim.quality
        domains.add(claim.domain)
        tiers.add(claim.tier)
        if claim.published_date and (newest is None or claim.published_date > newest):
            newest = claim.published_date
    total += 0.1 * max(0, min(3, len(domains)) - 1)
    return total, domains, tiers, newest


def _ids(assessments: list[Assessment]) -> list[str]:
    return list(_dedupe([a.claim_id for a in assessments]))


def _resolve_sides(
    support: list[Assessment],
    refute: list[Assessment],
    claim_by_id: dict[str, Claim],
    topic: str,
) -> Resolution | None:
    sw, sd, st, snew = _side_stats(support, claim_by_id)
    rw, rd, rt, rnew = _side_stats(refute, claim_by_id)
    if sw <= 0 or rw <= 0:
        return None
    if sw >= rw:
        winner, losing = "supports", "refutes"
        win_w, win_d, win_t, win_new = sw, sd, st, snew
        lose_w, lose_d, lose_t, lose_new = rw, rd, rt, rnew
    else:
        winner, losing = "refutes", "supports"
        win_w, win_d, win_t, win_new = rw, rd, rt, rnew
        lose_w, lose_d, lose_t, lose_new = sw, sd, st, snew
    margin = abs(sw - rw) / max(sw, rw)
    reason = None
    if "primary" in win_t and "primary" not in lose_t and win_w >= 0.6 * lose_w:
        reason = "primary_source_over_secondary"
    elif "primary" not in win_t and "primary" in lose_t and lose_w >= 0.6 * win_w:
        winner = losing
        win_w, lose_w = lose_w, win_w
        win_d, lose_d = lose_d, win_d
        win_t, lose_t = lose_t, win_t
        win_new, lose_new = lose_new, win_new
        reason = "primary_source_over_secondary"
        margin = abs(win_w - lose_w) / max(win_w, lose_w)
    elif margin >= 0.35 and len(win_d) >= 2:
        reason = "independent_domain_majority"
    elif win_new is not None and lose_new is not None and (win_new - lose_new).days >= 365 and margin >= 0.1:
        reason = "newer_source_over_older"
    elif margin >= 0.5:
        reason = "evidence_weight"
    if reason is None:
        return None
    confidence = min(0.9, 0.55 + margin * 0.3 + (0.1 if "primary" in win_t else 0.0))
    return Resolution(
        topic=topic,
        winner=winner,
        reason=reason,
        confidence=round(confidence, 3),
        evidence=_ids(support if winner == "supports" else refute),
        alternatives=[f"lost:{losing}"],
    )


def _assess_numeric(hyp: Hypothesis, claims: list[Claim]) -> HypothesisResult:
    observations = _numeric_observations(claims, hyp)
    if not observations:
        return HypothesisResult(hyp, "insufficient", 0.0, 0.0, "no_numeric_evidence")
    groups = _cluster_numeric(observations)
    anchors = _numeric_anchors(hyp)

    def group_score(g: list[_NumObs]) -> float:
        quality = sum(o.claim.quality for o in g)
        # Prefer the group whose local subject is actually the asked subject.
        # This keeps a page that mentions several numbers (database size,
        # string length, page count) from selecting the wrong one.
        fit = max((_jaccard(o.subject, anchors) for o in g), default=0.0) if anchors else 0.0
        return quality + fit

    group = max(groups, key=group_score)
    by_value: dict[float, list[_NumObs]] = {}
    for obs in group:
        by_value.setdefault(round(obs.value, 4), []).append(obs)
    values = sorted(by_value)
    if len(values) == 1:
        domains = {o.claim.domain for o in group}
        evidence = list(_dedupe([o.claim.id for o in group]))
        support = min(0.95, 0.55 + 0.1 * min(3, len(domains)))
        return HypothesisResult(
            hyp,
            "supported",
            round(support, 3),
            round(min(0.9, support), 3),
            "consistent_numeric_evidence",
            supporting=evidence,
        )

    def score(value: float) -> tuple[float, set[str], float, list[_NumObs]]:
        items = by_value[value]
        domains = {o.claim.domain for o in items}
        best = max(o.claim.quality for o in items)
        return best + 0.15 * min(3, len(domains)), domains, best, items

    ranked = sorted(values, key=lambda v: score(v)[0], reverse=True)
    first, second = ranked[0], ranked[1]
    s1, d1, _, items1 = score(first)
    s2, d2, _, items2 = score(second)
    margin = (s1 - s2) / max(s1, 1e-9)
    p1 = any(o.claim.tier == "primary" for o in items1)
    p2 = any(o.claim.tier == "primary" for o in items2)
    reason = None
    if p1 and not p2 and s1 >= 0.6 * s2:
        reason = "primary_source_over_secondary"
    elif p2 and not p1 and s2 >= 0.6 * s1:
        first, second = second, first
        s1, s2 = s2, s1
        d1, d2 = d2, d1
        items1, items2 = items2, items1
        p1, p2 = True, False
        reason = "primary_source_over_secondary"
    elif len(d1) >= 2 and len(d1) > len(d2) and margin >= 0.25:
        reason = "independent_domain_majority"
    else:
        newest1 = max((o.claim.published_date for o in items1 if o.claim.published_date), default=None)
        newest2 = max((o.claim.published_date for o in items2 if o.claim.published_date), default=None)
        if newest1 and newest2 and (newest1 - newest2).days >= 365 and margin >= 0.1:
            reason = "newer_source_over_older"
        elif margin >= 0.5:
            reason = "evidence_weight"

    evidence1 = list(_dedupe([o.claim.id for o in items1]))
    evidence2 = list(_dedupe([o.claim.id for o in items2]))
    subject = " ".join(sorted(group[0].subject)[:4]) or "value"
    if reason:
        resolution = Resolution(
            topic=f"numeric:{group[0].unit}:{subject}",
            winner=f"{first:g} {group[0].unit}",
            reason=reason,
            confidence=round(min(0.9, 0.55 + margin * 0.35 + (0.1 if p1 else 0.0)), 3),
            evidence=evidence1,
            alternatives=[f"{second:g} {group[0].unit}"],
        )
        support = min(0.95, 0.6 + 0.1 * min(3, len(d1)))
        return HypothesisResult(
            hyp,
            "supported",
            round(support, 3),
            resolution.confidence,
            reason,
            supporting=evidence1,
            refuting=evidence2,
            resolution=resolution,
        )
    return HypothesisResult(
        hyp,
        "conflicting",
        0.5,
        0.3,
        "unresolved_numeric_conflict",
        supporting=evidence1,
        refuting=evidence2,
    )


def _assess_hypothesis(
    hyp: Hypothesis,
    claims: list[Claim],
    assessments: list[Assessment],
    claim_by_id: dict[str, Claim],
) -> HypothesisResult:
    if hyp.kind == "numeric":
        return _assess_numeric(hyp, claims)
    relevant = [a for a in assessments if a.hypothesis_id == hyp.id and a.stance != "neutral"]
    support = [a for a in relevant if a.stance == "supports"]
    refute = [a for a in relevant if a.stance == "refutes"]

    if hyp.kind in {"definition", "comparison"}:
        if not support:
            return HypothesisResult(hyp, "insufficient", 0.0, 0.0, "no_supporting_evidence")
        sw, sd, _, _ = _side_stats(support, claim_by_id)
        support_score = min(1.0, sw / 1.2)
        if support_score < 0.35:
            return HypothesisResult(
                hyp,
                "insufficient",
                round(support_score, 3),
                0.2,
                "weak_evidence",
                supporting=_ids(support),
            )
        confidence = min(0.9, 0.45 + 0.2 * min(3, len(sd)) + 0.25 * support_score)
        return HypothesisResult(
            hyp,
            "supported",
            round(support_score, 3),
            round(confidence, 3),
            "evidence_describes_hypothesis",
            supporting=_ids(support),
        )

    if not support and not refute:
        return HypothesisResult(hyp, "insufficient", 0.0, 0.0, "no_relevant_evidence")
    if support and refute:
        resolution = _resolve_sides(support, refute, claim_by_id, hyp.statement)
        if resolution is not None:
            verdict: Verdict = "supported" if resolution.winner == "supports" else "refuted"
            support_w, _, _, _ = _side_stats(support, claim_by_id)
            refute_w, _, _, _ = _side_stats(refute, claim_by_id)
            total = support_w + refute_w
            support_share = support_w / total if total else 0.5
            return HypothesisResult(
                hyp,
                verdict,
                round(min(1.0, support_share), 3),
                resolution.confidence,
                resolution.reason,
                supporting=_ids(support),
                refuting=_ids(refute),
                resolution=resolution,
            )
        sw, _, _, _ = _side_stats(support, claim_by_id)
        rw, _, _, _ = _side_stats(refute, claim_by_id)
        total = sw + rw
        return HypothesisResult(
            hyp,
            "conflicting",
            round(sw / total if total else 0.5, 3),
            0.3,
            "unresolved_contradiction",
            supporting=_ids(support),
            refuting=_ids(refute),
        )
    if support:
        sw, sd, _, _ = _side_stats(support, claim_by_id)
        score = min(1.0, sw / 1.2)
        if score < 0.35:
            return HypothesisResult(
                hyp,
                "insufficient",
                round(score, 3),
                0.2,
                "weak_supporting_evidence",
                supporting=_ids(support),
            )
        confidence = min(0.9, 0.45 + 0.2 * min(3, len(sd)) + 0.25 * score)
        return HypothesisResult(
            hyp,
            "supported",
            round(score, 3),
            round(confidence, 3),
            "supporting_evidence_only",
            supporting=_ids(support),
        )
    rw, rd, _, _ = _side_stats(refute, claim_by_id)
    score = min(1.0, rw / 1.2)
    confidence = min(0.9, 0.45 + 0.2 * min(3, len(rd)) + 0.25 * score)
    return HypothesisResult(
        hyp,
        "refuted",
        0.0,
        round(confidence, 3),
        "refuting_evidence_only",
        refuting=_ids(refute),
    )


# -- outcome assembly ------------------------------------------------------


def _ordered_results(results: list[HypothesisResult]) -> list[HypothesisResult]:
    order = {"supported": 0, "refuted": 1, "conflicting": 2, "insufficient": 3}
    return sorted(
        results,
        key=lambda r: (
            order.get(r.verdict, 4),
            r.hypothesis.kind,
            r.hypothesis.statement.lower(),
        ),
    )


def _is_cited(claim: Claim) -> bool:
    f = claim.finding
    span = f.span
    return bool(f.url) and bool(f.fetched_at) and isinstance(span, list) and len(span) == 2 and 0 <= span[0] < span[1]


def _support_stats(
    claims: list[Claim],
    assessments: list[Assessment],
    results: list[HypothesisResult],
) -> dict:
    relevant = {a.claim_id for a in assessments if a.stance != "neutral"}
    winning: set[str] = set()
    losing: set[str] = set()
    contested: set[str] = set()
    for result in results:
        if result.hypothesis.kind == "numeric":
            relevant.update(result.supporting)
            relevant.update(result.refuting)
        if result.verdict == "supported":
            winning.update(result.supporting)
            losing.update(result.refuting)
        elif result.verdict == "refuted":
            winning.update(result.refuting)
            losing.update(result.supporting)
        elif result.verdict == "conflicting":
            contested.update(result.supporting)
            contested.update(result.refuting)
    winning -= losing
    winning -= contested
    losing -= winning
    cited = {c.id for c in claims if _is_cited(c)}
    denom = len(relevant)
    return {
        "claims": len(claims),
        "cited": len(cited),
        "relevant": len(relevant),
        "winning": len(winning),
        "contested": len(contested),
        "rate": round(len(winning) / denom, 3) if denom else 0.0,
        "citation_integrity": round(len(cited) / len(claims), 3) if claims else 1.0,
    }


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(" ,;:") + "..."


def _numeric_answer_quote(text: str, hyp: Hypothesis, limit: int = 320) -> str:
    """Quote the sentence that carries the numeric evidence.

    A source paragraph can begin with unrelated prose. Clipping from the start
    of the claim can hide the number that actually answered the question, so
    locate the most subject-relevant numeric match and quote around it.
    """

    anchors = _numeric_anchors(hyp)
    best: tuple[float, int, int] | None = None
    for match in NUM.finditer(text):
        before = text[max(0, match.start() - 160) : match.start()]
        subject = frozenset(t for t in tokenize(before) if len(t) > 2)
        fit = _jaccard(subject, anchors) if anchors else 0.0
        if best is None or fit > best[0]:
            best = (fit, match.start(), match.end())
    if best is None:
        return _clip(text, limit)
    _, start, end = best
    left = max(text.rfind("\n", 0, start), text.rfind(". ", 0, start))
    left = 0 if left < 0 else left + 1
    if left < len(text) and text[left] == " ":
        left += 1
    right_candidates = [i for i in (text.find("\n", end), text.find(". ", end)) if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    snippet = " ".join(text[left:right].split())
    return _clip(snippet or text[start:end], limit)


def _build_answer(results: list[HypothesisResult], claim_by_id: dict[str, Claim]) -> str:
    if not results:
        return "No testable hypotheses."
    parts: list[str] = []
    for result in _ordered_results(results)[:3]:
        hyp = result.hypothesis
        if result.verdict == "supported" and result.supporting:
            claim = claim_by_id.get(result.supporting[0])
            if claim:
                f = claim.finding
                quote = _numeric_answer_quote(f.claim, hyp) if hyp.kind == "numeric" else _clip(f.claim, 320)
                parts.append(f'{hyp.statement} - supported by "{quote}" ({f.url}, span {f.span[0]}-{f.span[1]}).')
                continue
        if result.verdict == "refuted" and result.refuting:
            claim = claim_by_id.get(result.refuting[0])
            if claim:
                f = claim.finding
                parts.append(
                    f'{hyp.statement} - contradicted by "{_clip(f.claim, 320)}" '
                    f"({f.url}, span {f.span[0]}-{f.span[1]})."
                )
                continue
        if result.verdict == "conflicting":
            parts.append(f"{hyp.statement} - contested by multiple sources; see resolutions.")
            continue
        parts.append(f"{hyp.statement} - insufficient evidence.")
    return " ".join(parts)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:48] or "hypothesis"


def _hypothesis_gaps(results: list[HypothesisResult]) -> list[str]:
    gaps: list[str] = []
    for result in results:
        if result.verdict == "insufficient":
            gaps.append(f"insufficient_evidence:{_slug(result.hypothesis.statement)}")
        elif result.verdict == "conflicting":
            gaps.append(f"unresolved_contradiction:{_slug(result.hypothesis.statement)}")
    return gaps[:8]


def synthesize(
    outcome: ResearchOutcome,
    *,
    query: str | None = None,
    budget: int | None = None,
) -> SynthesisOutcome:
    started = time.perf_counter()
    q = " ".join(((query if query is not None else outcome.query) or "").strip().split())
    budget = int(budget or outcome.budget or 8000)
    claims = _build_claims(outcome.findings)
    claim_by_id = {c.id: c for c in claims}
    hypotheses = generate_hypotheses(q)
    warnings = list(dict.fromkeys(outcome.warnings))
    gaps = list(dict.fromkeys(outcome.gaps))

    if not hypotheses:
        gap = "empty_query" if not q else "no_testable_hypothesis"
        result = SynthesisOutcome(
            status="no_reliable_result",
            query=q,
            hypotheses=[],
            claims=claims,
            assessments=[],
            resolutions=[],
            gaps=list(dict.fromkeys([*gaps, gap])),
            warnings=warnings,
            hops=[],
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            budget=budget,
            searched=list(outcome.searched),
        )
        result.tokens = result.payload()["tok"]
        return result

    assessments: list[Assessment] = []
    for hyp in hypotheses:
        for claim in claims:
            assessments.append(assess_claim(claim, hyp))
    results = [_assess_hypothesis(h, claims, assessments, claim_by_id) for h in hypotheses]

    numeric_resolved = any(r.resolution is not None and r.resolution.topic.startswith("numeric:") for r in results)
    if outcome.conflicts and not numeric_resolved:
        warnings.append("numeric_conflict_detected")
        gaps.append("unresolved_numeric_conflict")

    gaps = list(dict.fromkeys([*gaps, *_hypothesis_gaps(results)]))
    resolutions = [r.resolution for r in results if r.resolution is not None]

    if not claims:
        status = "no_reliable_result"
    elif any(r.verdict == "conflicting" for r in results):
        status = "conflicting_sources"
    elif all(r.verdict == "insufficient" for r in results):
        status = "no_reliable_result"
    elif any(r.verdict == "insufficient" for r in results) or any(g.startswith("no_source_for:") for g in gaps):
        status = "partial"
    else:
        status = "ok"

    if outcome.status == "possibly_outdated" and status in {"ok", "partial"}:
        status = "possibly_outdated"
        warnings.append("possibly_outdated_sources")

    result = SynthesisOutcome(
        status=status,
        query=q,
        hypotheses=results,
        claims=claims,
        assessments=assessments,
        resolutions=resolutions,
        gaps=gaps[:12],
        warnings=list(dict.fromkeys(warnings)),
        hops=[],
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        budget=budget,
        searched=list(outcome.searched),
        answer=_build_answer(results, claim_by_id),
    )
    result.tokens = result.payload()["tok"]
    return result


# -- bounded multi-hop follow-ups ------------------------------------------


def _norm_query(q: str) -> str:
    return re.sub(r"\W+", " ", (q or "").lower()).strip()


def followup_queries(
    outcome: SynthesisOutcome,
    already: list[str] | None = None,
    limit: int = 2,
) -> list[str]:
    seen = {_norm_query(q) for q in (already or [])}
    out: list[str] = []
    for result in _ordered_results(outcome.hypotheses):
        if result.verdict == "insufficient":
            suffix = " evidence"
        elif result.verdict == "conflicting":
            suffix = " primary source"
        else:
            continue
        base = result.hypothesis.statement
        if base.startswith("Not (") and base.endswith(")"):
            base = base[5:-1]
        query = clean_query(f"{base}{suffix}")
        if not query or _norm_query(query) in seen or query in out:
            continue
        out.append(query)
        if len(out) >= limit:
            break
    return out


def _covered(term: str, covered: set[str]) -> bool:
    if term in covered:
        return True
    if len(term) < 4:
        return False
    return any(len(token) >= 4 and (token.startswith(term) or term.startswith(token)) for token in covered)


def _merge(
    query: str,
    findings: list[Finding],
    gaps: list[str],
    searched: list[str],
    warnings: list[str],
    budget: int,
    status: str,
) -> ResearchOutcome:
    terms, _ = query_terms(query)
    covered: set[str] = set()
    for finding in findings:
        covered |= set(tokenize(finding.claim))
        if finding.heading:
            covered |= set(tokenize(finding.heading))
    missing = [t for t in terms if not _covered(t, covered) and t not in GAP_IGNORE and t not in FRESH]
    base_gaps = [
        g
        for g in dict.fromkeys(gaps)
        if not g.startswith(("no_source_for:", "no_search_results", "no_supported_claim"))
    ]
    merged_gaps = [*base_gaps, *[f"no_source_for:{t}" for t in missing[:6]]]
    if not findings and not merged_gaps:
        merged_gaps.append("no_supported_claim")
    merged = ResearchOutcome(
        status="ok" if findings else "no_reliable_result",
        query=query,
        findings=findings,
        gaps=merged_gaps,
        searched=list(dict.fromkeys(searched)),
        elapsed_ms=0,
        tokens=0,
        warnings=list(dict.fromkeys(warnings)),
        conflicts=detect_conflicts(findings, query),
        budget=budget,
    )
    if status == "possibly_outdated":
        merged.status = "possibly_outdated"
    elif merged.conflicts:
        merged.status = "conflicting_sources"
    return merged


class SynthesisEngine:
    """Run research, test hypotheses, and stop after bounded follow-up hops."""

    def __init__(self, research: ResearchEngine):
        self.research = research

    async def run(
        self,
        query: str,
        *,
        max_tokens: int | None = None,
        max_hops: int = 2,
        max_searches: int = 4,
        max_pages: int = 6,
        max_followups: int = 2,
    ) -> SynthesisOutcome:
        started = time.perf_counter()
        original = " ".join((query or "").strip().split())
        budget = resolve_budget(
            max_tokens,
            self.research.s.max_research_tokens,
            minimum=300,
            maximum=8000,
        )
        if not original:
            empty = synthesize(
                ResearchOutcome(
                    status="no_reliable_result",
                    query="",
                    findings=[],
                    gaps=["empty_query"],
                    searched=[],
                    elapsed_ms=0,
                    tokens=0,
                    budget=budget,
                ),
                query="",
                budget=budget,
            )
            empty.elapsed_ms = int((time.perf_counter() - started) * 1000)
            return empty

        max_hops = max(1, min(3, max_hops))
        max_followups = max(0, min(3, max_followups))
        merged_findings: list[Finding] = []
        seen: set[tuple] = set()
        searched: list[str] = []
        warnings: list[str] = []
        gaps: list[str] = []
        run_status = "ok"
        queries = [original]
        hops: list[dict] = []
        synth: SynthesisOutcome | None = None

        for hop in range(max_hops):
            hop_outcomes: list[ResearchOutcome] = []
            for q in queries:
                try:
                    out = await self.research.research(
                        q,
                        max_tokens=min(4000, max(1200, budget)),
                        max_searches=max_searches,
                        max_pages=max_pages,
                    )
                except Exception as exc:  # noqa: BLE001 - contain one failed hop
                    warnings.append(f"research_failed:{type(exc).__name__}")
                    continue
                hop_outcomes.append(out)
                searched.extend(out.searched)
                gaps.extend(out.gaps)
                warnings.extend(out.warnings)
                if out.status == "possibly_outdated":
                    run_status = "possibly_outdated"

            new_count = 0
            for out in hop_outcomes:
                for finding in out.findings:
                    key = _finding_key(finding)
                    if key in seen:
                        continue
                    seen.add(key)
                    merged_findings.append(finding)
                    new_count += 1

            merged = _merge(
                original,
                merged_findings,
                gaps,
                searched,
                warnings,
                budget,
                run_status,
            )
            synth = synthesize(merged, query=original, budget=budget)
            hops.append(
                {
                    "q": list(queries),
                    "new": new_count,
                    "n": len(merged_findings),
                    "v": [r.verdict for r in _ordered_results(synth.hypotheses)[:4]],
                }
            )

            if new_count == 0 and hop > 0:
                hops[-1]["stop"] = "no_new_evidence"
                break
            if synth.hypotheses and all(r.verdict in {"supported", "refuted"} for r in synth.hypotheses):
                hops[-1]["stop"] = "resolved"
                break
            if hop == max_hops - 1:
                hops[-1]["stop"] = "max_hops"
                break
            followups = followup_queries(synth, searched, limit=max_followups)
            if not followups:
                hops[-1]["stop"] = "no_followups"
                break
            queries = followups

        if synth is None:
            merged = _merge(
                original,
                merged_findings,
                gaps,
                searched,
                warnings,
                budget,
                run_status,
            )
            synth = synthesize(merged, query=original, budget=budget)

        synth.hops = hops
        synth.searched = list(dict.fromkeys(searched))
        synth.elapsed_ms = int((time.perf_counter() - started) * 1000)
        synth.tokens = synth.payload()["tok"]
        return synth
