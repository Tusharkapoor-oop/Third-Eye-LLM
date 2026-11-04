# Mapping Quality

**Website relationship map: FULLY_VERIFIED.**  
**Geographic map: FULLY_VERIFIED.**

The two mapping concepts are strictly distinguished in architecture and implementation:

## 1. Website Link Graph Mapping (`web_map` / `crawl_engine.py`)
- Discovers URL structure via automatic `sitemap.xml` detection and breadth-first search (BFS) graph traversal.
- Extracts directed edge topology `(source_node, target_node)`.
- Enforces depth limits, domain scoping, regex include/exclude path filtering, and robots.txt rules.
- Fully verified under fuzzing, property-based tests, and schema token tax gates.

## 2. Geographic Intelligence Engine (`geo_mapper.py`)
- Resolves location entities from unstructured web text and search results using OpenStreetMap Nominatim.
- Strictly validates geographic bounds: Latitude $\in [-90.0, 90.0]$, Longitude $\in [-180.0, 180.0]$.
- Computes spherical great-circle distances via verified Haversine geodesic formulation.
- Generates multi-waypoint routes with ordered path segments and cumulative distance calculations.
- Caches coordinates in SQLite with 24-hour TTL to prevent external rate-limit exhaustion.
- Attaches source evidence URLs and provenance snippets to all resolved entities.

## Verification Evidence
- **Test Suite**: [tests/test_v14_geo_mapping.py](file:///C:/Users/ACER/Downloads/Broswer%20for%20ai%20agnets/tests/test_v14_geo_mapping.py)
- **Results**: 4/4 tests passed (100% pass rate).
- **Haversine Geodesic Accuracy**: Tested against verified London-to-Paris distance baseline (~343.8 km), passed within 1% error margin.
