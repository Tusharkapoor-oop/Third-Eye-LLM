"""Wikipedia search adapter (official MediaWiki API, keyless).

Used as a last-resort provider for encyclopedic queries. It is not a general
web search engine and is labelled as such in provenance.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from ..errors import ErrCode, ProviderError
from ..net import SafeFetcher
from .base import Hit, clean_snippet, make_hit

_FRENCH = {
    "quelle",
    "quel",
    "quels",
    "quelles",
    "capitale",
    "fleuve",
    "rivière",
    "plus",
    "long",
    "longue",
    "pays",
    "comment",
    "pourquoi",
    "allemagne",
    "france",
    "monde",
    "est",
    "sont",
}
_GERMAN = {
    "welche",
    "welcher",
    "welches",
    "hauptstadt",
    "ist",
    "sind",
    "der",
    "die",
    "das",
    "und",
    "von",
    "deutschland",
    "größte",
    "groesste",
    "fluss",
}
_SPANISH = {
    "cuál",
    "cual",
    "capital",
    "más",
    "mas",
    "largo",
    "larga",
    "río",
    "rio",
    "américa",
    "america",
    "del",
    "país",
    "pais",
    "quién",
    "quien",
    "es",
    "son",
    "cuál es",
}


def _guess_language(query: str) -> str:
    """Pick a Wikipedia language for obvious non-English queries.

    This is a cheap stop-word heuristic, not full language detection. It fixes
    the common failure where an English Wikipedia search returns unrelated
    pages for a French, German, or Spanish question.
    """
    # Check kana before CJK ideographs: Japanese questions usually contain
    # kanji too, so testing the Han range first would misclassify them as zh.
    if re.search(r"[\u3040-\u30ff]", query):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", query):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", query):
        return "zh"
    if re.search(r"[\u0400-\u04ff]", query):
        return "ru"
    words = set(re.findall(r"[a-zà-ÿß]+", query.lower()))
    scores = {
        "fr": len(words & _FRENCH),
        "de": len(words & _GERMAN),
        "es": len(words & _SPANISH),
    }
    lang, score = max(scores.items(), key=lambda kv: kv[1])
    return lang if score >= 2 else "en"


class WikipediaSearch:
    name = "wikipedia"
    timeout_s = 4.0

    def __init__(self, fetcher: SafeFetcher, lang: str = "en"):
        self.fetcher = fetcher
        self.lang = lang

    async def search(
        self,
        query: str,
        *,
        k: int = 5,
        freshness: str | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[Hit]:
        if domains and not any(d.endswith("wikipedia.org") for d in domains):
            return []
        lang = _guess_language(query) if self.lang == "en" else self.lang
        url = (
            f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={quote(query)}&srlimit={min(10, max(1, k))}"
            "&srprop=snippet%7Ctimestamp&format=json&formatversion=2&origin=*"
        )
        resp = await self.fetcher.fetch(
            url,
            headers={"Accept": "application/json"},
            cache_ttl=1800,
            max_bytes=1_000_000,
        )
        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError("wikipedia returned invalid JSON", code=ErrCode.PROVIDER) from e
        if "error" in data:
            raise ProviderError("wikipedia API error", code=ErrCode.PROVIDER)
        hits: list[Hit] = []
        for i, item in enumerate((data.get("query") or {}).get("search") or []):
            if len(hits) >= k:
                break
            title = item.get("title", "")
            snippet = clean_snippet(re.sub(r"<[^>]+>", " ", item.get("snippet", "")))
            hit = make_hit(
                title,
                f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                snippet,
                provider=self.name,
                rank=i,
                date_hint=item.get("timestamp", ""),
            )
            if hit:
                hits.append(hit)
        return hits
