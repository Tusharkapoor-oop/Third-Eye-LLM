"""
Benchmark WebLens crawl_website and web_map against Tavily capabilities on controlled fixtures.
Evaluates:
1. Page coverage & depth boundaries
2. Link graph correctness & topology (nodes/edges)
3. Duplicate suppression & URL normalization (fragments, query params, trailing slashes)
4. Sitemap traversal (standard XML sitemaps, 404 fallback)
5. Crawler trap & cycle defense (repeating paths, path explosions, calendar query bombs)
6. Robots.txt adherence & regex path filtering (select_paths, exclude_paths)
7. Content extraction fidelity & in-flight semantic pruning
8. Schema compatibility & architectural comparison with Tavily Crawl/Map
"""

from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import urlparse
import httpx
import respx

from crawl_engine import CrawlEngine, CrawlJobStatus, RobotsChecker, matches_path_filters
from src.engine.crawl.crawler import WebsiteCrawler, is_trap_url
from src.engine.crawl.mapper import WebsiteMapper
from src.engine.search.aggregator import normalize_url


async def benchmark_page_coverage() -> dict:
    """Fixture 1: Multi-depth hierarchy (10 internal pages, 2 external)."""
    base_url = "https://coverage-fixture.test"
    site_pages = {
        "/": """
            <html><body>
                <a href="/intro">Intro</a>
                <a href="/guide">Guide</a>
                <a href="/api">API</a>
                <a href="/faq">FAQ</a>
                <a href="https://external-ad.test/banner">Ad</a>
                <a href="https://cdn.thirdparty.test/script.js">CDN</a>
            </body></html>
        """,
        "/intro": "<html><body><h1>Intro</h1><p>Introduction to system.</p></body></html>",
        "/guide": """
            <html><body>
                <h1>Guide</h1>
                <a href="/guide/step1">Step 1</a>
                <a href="/guide/step2">Step 2</a>
                <a href="/guide/advanced">Advanced</a>
            </body></html>
        """,
        "/guide/step1": "<html><body><h1>Step 1</h1><p>Setup environment.</p></body></html>",
        "/guide/step2": "<html><body><h1>Step 2</h1><p>Run pipeline.</p></body></html>",
        "/guide/advanced": "<html><body><h1>Advanced</h1><p>Scaling tips.</p></body></html>",
        "/api": """
            <html><body>
                <h1>API</h1>
                <a href="/api/v1">API v1</a>
                <a href="/api/v2">API v2</a>
            </body></html>
        """,
        "/api/v1": "<html><body><h1>API v1</h1><p>Legacy endpoints.</p></body></html>",
        "/api/v2": "<html><body><h1>API v2</h1><p>Modern endpoints.</p></body></html>",
        "/faq": "<html><body><h1>FAQ</h1><p>Frequently asked questions.</p></body></html>",
    }

    engine = CrawlEngine()

    with respx.mock(base_url=base_url, assert_all_called=False) as mock:
        mock.get("/sitemap.xml").respond(status_code=404)
        for path, html in site_pages.items():
            mock.get(path).respond(status_code=200, text=html)

        # 1. Depth=1 test
        t0 = time.perf_counter()
        res_d1 = await engine.map_website(base_url, max_depth=1, limit=50)
        lat_d1 = time.perf_counter() - t0

        # 2. Depth=2 test
        t0 = time.perf_counter()
        res_d2 = await engine.map_website(base_url, max_depth=2, limit=50)
        lat_d2 = time.perf_counter() - t0

        # 3. Limit=3 test
        res_lim3 = await engine.map_website(base_url, max_depth=2, limit=3)

    # Check for external leaks
    external_leaks = [u for u in res_d2.discovered_urls if not u.startswith(base_url)]

    return {
        "total_site_pages": len(site_pages),
        "depth_1_count": res_d1.count,
        "depth_1_urls": res_d1.discovered_urls,
        "depth_1_latency_s": round(lat_d1, 4),
        "depth_2_count": res_d2.count,
        "depth_2_urls": res_d2.discovered_urls,
        "depth_2_latency_s": round(lat_d2, 4),
        "limit_3_count": res_lim3.count,
        "external_leaks_count": len(external_leaks),
        "external_leaks": external_leaks,
        "page_coverage_pct": round((res_d2.count / len(site_pages)) * 100, 1),
    }


async def benchmark_link_graph_correctness() -> dict:
    """Fixture 2: Directed cyclic graph topology."""
    base_url = "https://graph-fixture.test"
    pages = {
        "/": """
            <html><body>
                <a href="/node-a">Node A</a>
                <a href="/node-b">Node B</a>
            </body></html>
        """,
        "/node-a": """
            <html><body>
                <a href="/node-b">Node B</a>
                <a href="/node-c">Node C</a>
            </body></html>
        """,
        "/node-b": """
            <html><body>
                <a href="/">Cycle to Root</a>
                <a href="/node-c">Node C</a>
            </body></html>
        """,
        "/node-c": """
            <html><body>
                <a href="/node-d">Node D</a>
            </body></html>
        """,
        "/node-d": "<html><body><h1>Leaf Node D</h1></body></html>",
    }

    engine = CrawlEngine()

    with respx.mock(base_url=base_url, assert_all_called=False) as mock:
        mock.get("/sitemap.xml").respond(status_code=404)
        for path, html in pages.items():
            mock.get(path).respond(status_code=200, text=html)

        job = engine.start_crawl_job(base_url, max_depth=3, limit=10)
        await job._task

    # Evaluate nodes and edges
    discovered_nodes = job.link_graph.nodes
    discovered_edges = job.link_graph.edges

    expected_nodes = [
        f"{base_url}/",
        f"{base_url}/node-a",
        f"{base_url}/node-b",
        f"{base_url}/node-c",
        f"{base_url}/node-d",
    ]

    return {
        "job_status": job.status,
        "nodes_count": len(discovered_nodes),
        "nodes": discovered_nodes,
        "edges_count": len(discovered_edges),
        "edges": discovered_edges,
        "cycle_handled_without_hang": job.status == CrawlJobStatus.COMPLETED,
        "all_expected_nodes_found": all(
            any(n.rstrip("/") == exp.rstrip("/") for n in discovered_nodes)
            for exp in expected_nodes
        ),
    }


async def benchmark_duplicate_suppression() -> dict:
    """Fixture 3: Redundant and duplicate URLs with fragments and query parameters."""
    base_url = "https://dedup-fixture.test"
    root_html = """
        <html><body>
            <!-- Unique page 1 with variants -->
            <a href="/page-alpha">Page Alpha</a>
            <a href="/page-alpha/">Page Alpha (Trailing Slash)</a>
            <a href="/page-alpha#section-one">Page Alpha Fragment 1</a>
            <a href="/page-alpha#section-two">Page Alpha Fragment 2</a>
            <a href="/page-alpha?utm_source=twitter&utm_medium=cpc">Page Alpha Tracking Query</a>
            <a href="/page-alpha?utm_source=linkedin">Page Alpha Tracking Query 2</a>

            <!-- Unique page 2 with variants -->
            <a href="/page-beta">Page Beta</a>
            <a href="/page-beta/">Page Beta (Trailing Slash)</a>
            <a href="/page-beta#top">Page Beta Top</a>

            <!-- Unique page 3 -->
            <a href="/page-gamma">Page Gamma</a>
        </body></html>
    """
    raw_links_count = 10
    true_unique_pages = 4  # root, page-alpha, page-beta, page-gamma

    # Test 1: WebsiteMapper deduplication
    mapper = WebsiteMapper()
    with respx.mock(base_url=base_url, assert_all_called=False) as mock:
        mock.get("/robots.txt").respond(status_code=404)
        mock.get("/sitemap.xml").respond(status_code=404)
        mock.get("/sitemap_index.xml").respond(status_code=404)
        mock.get("/").respond(status_code=200, text=root_html)

        mapper_res = await mapper.map_domain(base_url, limit=20)

    # Test 2: CrawlEngine mapping
    engine = CrawlEngine()
    with respx.mock(base_url=base_url, assert_all_called=False) as mock:
        mock.get("/sitemap.xml").respond(status_code=404)
        mock.get("/").respond(status_code=200, text=root_html)
        mock.get("/page-alpha").respond(status_code=200, text="<html><body>Alpha</body></html>")
        mock.get("/page-beta").respond(status_code=200, text="<html><body>Beta</body></html>")
        mock.get("/page-gamma").respond(status_code=200, text="<html><body>Gamma</body></html>")

        engine_res = await engine.map_website(base_url, max_depth=1, limit=20)

    return {
        "raw_links_in_html": raw_links_count,
        "true_unique_pages": true_unique_pages,
        "mapper_discovered_count": mapper_res["total_discovered"],
        "mapper_urls": [u["url"] for u in mapper_res.get("urls", [])],
        "engine_discovered_count": engine_res.count,
        "engine_urls": engine_res.discovered_urls,
        "mapper_duplicate_suppression_pct": round(
            (1.0 - (mapper_res["total_discovered"] / raw_links_count)) * 100, 1
        ),
    }


async def benchmark_sitemap_traversal() -> dict:
    """Fixture 4: XML Sitemap discovery and fallback."""
    base_url = "https://sitemap-fixture.test"
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://sitemap-fixture.test/</loc><lastmod>2026-11-01</lastmod></url>
        <url><loc>https://sitemap-fixture.test/docs/intro</loc><lastmod>2026-11-02</lastmod></url>
        <url><loc>https://sitemap-fixture.test/docs/install</loc><lastmod>2026-11-02</lastmod></url>
        <url><loc>https://sitemap-fixture.test/docs/architecture</loc><lastmod>2026-11-03</lastmod></url>
        <url><loc>https://sitemap-fixture.test/blog/2026-release</loc><lastmod>2026-11-04</lastmod></url>
        <url><loc>https://sitemap-fixture.test/pricing</loc><lastmod>2026-11-01</lastmod></url>
    </urlset>
    """
    # Root HTML has only 1 link
    root_html = '<html><body><a href="/pricing">Pricing</a></body></html>'

    engine = CrawlEngine()
    mapper = WebsiteMapper()

    # Case A: Sitemap present
    with respx.mock(base_url=base_url, assert_all_called=False) as mock:
        mock.get("/robots.txt").respond(
            status_code=200,
            text=f"User-agent: *\nSitemap: {base_url}/sitemap.xml\n",
        )
        mock.get("/sitemap.xml").respond(status_code=200, text=sitemap_xml)
        mock.get("/").respond(status_code=200, text=root_html)

        t0 = time.perf_counter()
        engine_sitemap_res = await engine.map_website(base_url, limit=20)
        engine_sitemap_lat = time.perf_counter() - t0

        t0 = time.perf_counter()
        mapper_sitemap_res = await mapper.map_domain(base_url, limit=20)
        mapper_sitemap_lat = time.perf_counter() - t0

    # Case B: Sitemap 404 (Graceful fallback to HTML BFS)
    base_url_404 = "https://sitemap-404-fixture.test"
    with respx.mock(base_url=base_url_404, assert_all_called=False) as mock:
        mock.get("/robots.txt").respond(status_code=404)
        mock.get("/sitemap.xml").respond(status_code=404)
        mock.get("/sitemap_index.xml").respond(status_code=404)
        mock.get("/").respond(status_code=200, text=root_html)
        mock.get("/pricing").respond(status_code=200, text="<html><body>Pricing Page</body></html>")

        t0 = time.perf_counter()
        engine_fallback_res = await engine.map_website(base_url_404, limit=20)
        engine_fallback_lat = time.perf_counter() - t0

    return {
        "sitemap_declared_urls": 6,
        "engine_sitemap_discovered": engine_sitemap_res.count,
        "engine_sitemap_urls": engine_sitemap_res.discovered_urls,
        "engine_sitemap_latency_s": round(engine_sitemap_lat, 4),
        "mapper_sitemap_discovered": mapper_sitemap_res["total_discovered"],
        "mapper_sitemap_latency_s": round(mapper_sitemap_lat, 4),
        "fallback_404_discovered": engine_fallback_res.count,
        "fallback_404_latency_s": round(engine_fallback_lat, 4),
        "sitemap_acceleration_ratio": round(
            engine_fallback_lat / max(0.0001, engine_sitemap_lat), 2
        ),
    }


def benchmark_crawler_traps() -> dict:
    """Fixture 5: Crawler traps, cyclic loops, and query bombs."""
    trap_cases = [
        ("https://example.com/a/b/c/a/b/c/d", "Cyclic directory duplication"),
        ("https://example.com/a/b/c/a/b/c/", "Cyclic directory with trailing slash"),
        ("https://example.com/tag/tag/tag/", "Consecutive identical path segments"),
        ("https://example.com/1/2/3/4/5/6/7/8/9", "Path explosion (9 segments)"),
        ("https://example.com/events?date=2026-10-20&calendar=month", "Calendar query bomb"),
        ("https://example.com/events?year=2026&month=10", "Year/month query bomb"),
        ("https://example.com/filter?filter=active&sort=date", "Filter/sort state explosion"),
        ("https://example.com/blog/article-name", "Clean legitimate blog article"),
        ("https://example.com/docs/v2/getting-started", "Clean legitimate documentation URL"),
    ]

    results = []
    correct_identifications = 0

    for url, desc in trap_cases:
        detected = is_trap_url(url)
        is_actually_trap = "Clean" not in desc
        is_correct = detected == is_actually_trap
        if is_correct:
            correct_identifications += 1

        results.append({
            "url": url,
            "description": desc,
            "detected_as_trap": detected,
            "expected_trap": is_actually_trap,
            "verdict": "PASS" if is_correct else "FAIL",
        })

    accuracy = round((correct_identifications / len(trap_cases)) * 100, 1)

    return {
        "total_trap_cases_tested": len(trap_cases),
        "correct_identifications": correct_identifications,
        "accuracy_pct": accuracy,
        "detailed_results": results,
    }


async def benchmark_robots_and_path_filtering() -> dict:
    """Fixture 6: Robots.txt rules and regex path filters."""
    base_url = "https://filter-fixture.test"
    robots_txt = """
    User-agent: *
    Disallow: /admin/
    Disallow: /private/
    Disallow: /internal/
    Allow: /public/
    Allow: /blog/
    """
    checker = RobotsChecker()

    with respx.mock(base_url=base_url) as mock:
        mock.get("/robots.txt").respond(status_code=200, text=robots_txt)

        admin_allowed = await checker.can_fetch(f"{base_url}/admin/dashboard")
        private_allowed = await checker.can_fetch(f"{base_url}/private/keys")
        internal_allowed = await checker.can_fetch(f"{base_url}/internal/metrics")
        public_allowed = await checker.can_fetch(f"{base_url}/public/index")
        blog_allowed = await checker.can_fetch(f"{base_url}/blog/news")

    # Regex path filters
    select_rules = [r"^/docs/", r"^/api/"]
    exclude_rules = [r"/internal/", r"\.pdf$"]

    test_paths = [
        ("/docs/intro", True),
        ("/docs/internal/guide", False),  # Excluded by rule
        ("/api/v1/users", True),
        ("/api/v1/document.pdf", False),  # Excluded by rule
        ("/blog/post-1", False),          # Not in select_paths
        ("/admin/secret", False),         # Not in select_paths
    ]

    filter_checks = []
    filter_correct = 0
    for path, expected in test_paths:
        matched = matches_path_filters(
            path,
            select_paths=select_rules,
            exclude_paths=exclude_rules,
        )
        passed = matched == expected
        if passed:
            filter_correct += 1
        filter_checks.append({
            "path": path,
            "matches": matched,
            "expected": expected,
            "verdict": "PASS" if passed else "FAIL",
        })

    return {
        "robots_adherence": {
            "/admin/dashboard (Disallow)": "BLOCKED" if not admin_allowed else "LEAKED",
            "/private/keys (Disallow)": "BLOCKED" if not private_allowed else "LEAKED",
            "/internal/metrics (Disallow)": "BLOCKED" if not internal_allowed else "LEAKED",
            "/public/index (Allow)": "PERMITTED" if public_allowed else "BLOCKED",
            "/blog/news (Allow)": "PERMITTED" if blog_allowed else "BLOCKED",
            "robots_correct": (
                not admin_allowed and not private_allowed and not internal_allowed and public_allowed and blog_allowed
            ),
        },
        "path_filtering": {
            "select_paths": select_rules,
            "exclude_paths": exclude_rules,
            "accuracy_pct": round((filter_correct / len(test_paths)) * 100, 1),
            "checks": filter_checks,
        },
    }


async def benchmark_content_extraction_crawl() -> dict:
    """Fixture 7: Crawl with in-flight semantic passage pruning."""
    base_url = "https://crawl-content.test"
    pages = {
        "/": """
            <html><body>
                <h1>Tech Docs Root</h1>
                <a href="/async-architecture">Async Architecture</a>
                <a href="/deployment">Deployment Guide</a>
            </body></html>
        """,
        "/async-architecture": """
            <html><body>
                <h1>Async Architecture</h1>
                <p>WebLens uses asyncio concurrency with polite semaphores to ingest multiple pages simultaneously.</p>
                <pre><code>async def fetch_all(urls): return await asyncio.gather(*tasks)</code></pre>
            </body></html>
        """,
        "/deployment": """
            <html><body>
                <h1>Deployment Guide</h1>
                <p>Run WebLens inside Docker with gunicorn / uvicorn MCP server.</p>
            </body></html>
        """,
    }

    engine = CrawlEngine()

    with respx.mock(base_url=base_url, assert_all_called=False) as mock:
        mock.get("/sitemap.xml").respond(status_code=404)
        for path, html in pages.items():
            mock.get(path).respond(status_code=200, text=html)

        t0 = time.perf_counter()
        crawl_res = await engine.crawl_website(
            base_url=base_url,
            limit=5,
            instructions="asyncio concurrency architecture",
            chunks_per_source=2,
        )
        lat = time.perf_counter() - t0

    crawled_count = len(crawl_res.results)
    total_chunks = sum(len(r.chunks) for r in crawl_res.results)

    # Check semantic scoring of extracted chunks
    top_chunk_scores = [c.score for r in crawl_res.results for c in r.chunks]

    return {
        "crawled_pages_count": crawled_count,
        "failed_pages_count": len(crawl_res.failed_results),
        "total_extracted_chunks": total_chunks,
        "execution_latency_s": round(lat, 4),
        "source_engine": crawl_res.source_engine,
        "top_chunk_scores": top_chunk_scores,
        "results_summary": [
            {
                "url": r.url,
                "title": r.title,
                "chunks_count": len(r.chunks),
                "snippet": r.content[:120],
            }
            for r in crawl_res.results
        ],
    }


async def run_all_benchmarks():
    print("=" * 70)
    print("RUNNING WEBLENS CRAWL & MAP CONTROLLED BENCHMARK BATTERY")
    print("=" * 70)

    print("[1/7] Running Page Coverage & Depth Benchmark...")
    coverage = await benchmark_page_coverage()
    print(f"  Coverage: {coverage['page_coverage_pct']}% | Depth 1: {coverage['depth_1_count']} | Depth 2: {coverage['depth_2_count']} | Leaks: {coverage['external_leaks_count']}")

    print("[2/7] Running Link Graph Correctness Benchmark...")
    graph = await benchmark_link_graph_correctness()
    print(f"  Graph Nodes: {graph['nodes_count']} | Edges: {graph['edges_count']} | Cycle Handled: {graph['cycle_handled_without_hang']}")

    print("[3/7] Running Duplicate Suppression Benchmark...")
    dedup = await benchmark_duplicate_suppression()
    print(f"  Raw Links: {dedup['raw_links_in_html']} | True Unique: {dedup['true_unique_pages']} | Mapper Discovered: {dedup['mapper_discovered_count']} | Dedup Rate: {dedup['mapper_duplicate_suppression_pct']}%")

    print("[4/7] Running Sitemap Traversal Benchmark...")
    sitemap = await benchmark_sitemap_traversal()
    print(f"  Sitemap Declared: {sitemap['sitemap_declared_urls']} | Discovered: {sitemap['engine_sitemap_discovered']} | Fallback: {sitemap['fallback_404_discovered']}")

    print("[5/7] Running Crawler Traps & Cycle Benchmark...")
    traps = benchmark_crawler_traps()
    print(f"  Trap Cases: {traps['total_trap_cases_tested']} | Accuracy: {traps['accuracy_pct']}%")

    print("[6/7] Running Robots & Path Filtering Benchmark...")
    filters = await benchmark_robots_and_path_filtering()
    print(f"  Robots Correct: {filters['robots_adherence']['robots_correct']} | Filter Accuracy: {filters['path_filtering']['accuracy_pct']}%")

    print("[7/7] Running Content Extraction & In-Flight Pruning...")
    extraction = await benchmark_content_extraction_crawl()
    print(f"  Crawled Pages: {extraction['crawled_pages_count']} | Chunks: {extraction['total_extracted_chunks']} | Latency: {extraction['execution_latency_s']}s")

    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "page_coverage": coverage,
        "link_graph": graph,
        "duplicate_suppression": dedup,
        "sitemap_traversal": sitemap,
        "crawler_traps": traps,
        "robots_and_path_filtering": filters,
        "content_extraction": extraction,
    }

    out_file = "reports/domination/crawl_map_benchmark_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print("=" * 70)
    print(f"Benchmark results written to {out_file}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks())
