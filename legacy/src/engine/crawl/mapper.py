"""
Website Topology and Sitemap Mapper
Discovers URL structure and available pages via sitemaps and root link extraction.
"""

from __future__ import annotations

try:
    from defusedxml.ElementTree import fromstring as safe_xml_fromstring
except ImportError:
    from xml.etree.ElementTree import fromstring as safe_xml_fromstring  # type: ignore[no-redef] # nosec B405
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.engine.crawl.robots import RobotsManager
from src.engine.search.aggregator import get_domain, normalize_url
from src.engine.security import safe_fetch_url, validate_url_security


class WebsiteMapper:
    def __init__(self):
        self.robots_manager = RobotsManager()

    async def map_domain(self, seed_url: str, limit: int = 30) -> dict:
        is_safe, reason, _ = validate_url_security(seed_url)
        if not is_safe:
            return {"error": f"Security block: {reason}", "urls": [], "total_discovered": 0}

        parsed = urlparse(seed_url)
        domain = get_domain(seed_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Check for sitemaps in robots.txt
        await self.robots_manager.get_parser(domain)
        sitemap_urls = self.robots_manager.get_sitemaps_for_domain(domain)
        if not sitemap_urls:
            sitemap_urls = [f"{base_origin}/sitemap.xml", f"{base_origin}/sitemap_index.xml"]

        discovered_urls: list[dict] = []
        seen: set[str] = set()
        sitemap_found = False

        for sm_url in sitemap_urls:
            try:
                code, raw_bytes, _, _ = await safe_fetch_url(sm_url)
                if code == 200 and raw_bytes:
                    root = safe_xml_fromstring(raw_bytes)  # nosec B314
                    sitemap_found = True
                    # Check for sitemap index vs urlset
                    # Namespaces often used: http://www.sitemaps.org/schemas/sitemap/0.9
                    for elem in root.iter():
                        tag = elem.tag.split("}")[-1]
                        if tag == "url" or tag == "sitemap":
                            loc = ""
                            lastmod = ""
                            for child in elem:
                                c_tag = child.tag.split("}")[-1]
                                if c_tag == "loc" and child.text:
                                    loc = child.text.strip()
                                elif c_tag == "lastmod" and child.text:
                                    lastmod = child.text.strip()

                            if loc and loc.startswith("http"):
                                clean_u = normalize_url(loc)
                                if clean_u not in seen and get_domain(clean_u) == domain:
                                    seen.add(clean_u)
                                    item = {"url": clean_u}
                                    if lastmod:
                                        item["lastmod"] = lastmod
                                    discovered_urls.append(item)
                                    if len(discovered_urls) >= limit:
                                        break
                    if len(discovered_urls) >= limit:
                        break
            except Exception:
                continue

        # 2. If no sitemap or few URLs found, extract links from the seed HTML
        if len(discovered_urls) < 5:
            try:
                code, html_bytes, _, _ = await safe_fetch_url(seed_url)
                if code == 200 and html_bytes:
                    soup = BeautifulSoup(html_bytes, "html.parser")
                    for a in soup.find_all("a", href=True):
                        val = a.get("href")
                        raw_href = val.strip() if isinstance(val, str) else (val[0].strip() if isinstance(val, list) and val else "")
                        if not raw_href:
                            continue
                        abs_url = urljoin(seed_url, raw_href)
                        clean_u = normalize_url(abs_url)
                        if clean_u not in seen and get_domain(clean_u) == domain:
                            seen.add(clean_u)
                            link_text = a.get_text(strip=True)[:60]
                            entry = {"url": clean_u}
                            if link_text:
                                entry["title_hint"] = link_text
                            discovered_urls.append(entry)
                            if len(discovered_urls) >= limit:
                                break
            except Exception:
                pass

        return {
            "domain": domain,
            "seed_url": seed_url,
            "sitemap_found": sitemap_found,
            "urls": discovered_urls[:limit],
            "total_discovered": len(discovered_urls[:limit])
        }
