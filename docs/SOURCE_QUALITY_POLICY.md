# WebLens Source Quality and Authority Policy

## 1. Objective

Downstream AI agents rely on WebLens to establish the factual baseline for their decision-making. Ingesting content from search-engine optimization (SEO) link farms, low-quality automated scrapers, or untrusted aggregators severely degrades agent reasoning. This policy establishes the structural criteria for source inclusion, prioritization, and exclusion.

---

## 2. Evidence Tier Classification

WebLens classifies all candidate information sources into four formal evidentiary tiers:

### Tier 1: Primary Institutional & Regulatory Sources (Highest Confidence)
- **Scope:** Official governmental databases, national statistical bureaus, academic repositories, and regulatory filings.
- **Examples:** `.gov`, `.gov.in`, `.gov.uk`, `who.int`, `un.org`, `worldbank.org`, `sec.gov`, `census.gov`, `nih.gov`, `arxiv.org`.
- **Handling:** Prioritized in search routing with a 2.0x authority boost. Sufficient as single-source ground truth for factual assertions.

### Tier 2: Authoritative Encyclopedias & Official Documentation (High Confidence)
- **Scope:** Curated technical documentation, standard bodies, and peer-reviewed reference materials.
- **Examples:** `wikipedia.org`, `w3.org`, `docs.python.org`, `developer.mozilla.org`, `iso.org`, `rtings.com`.
- **Handling:** Receives a 1.5x authority boost. Serves as ground truth for technical API schemas, scientific terminology, and historical timelines.

### Tier 3: Verified Commercial Media & Company Portals (Medium Confidence)
- **Scope:** Established global journalistic institutions, verified corporate websites, and primary PR wires.
- **Examples:** `reuters.com`, `bloomberg.com`, `apnews.com`, verified company root domains (`apple.com`, `microsoft.com`).
- **Handling:** Neutral weighting (1.0x). Multiple independent sources required to verify disputed corporate or financial claims.

### Tier 4: Unverified User Content & Aggregators (Low Confidence / Filtered)
- **Scope:** Discussion forums, social media platforms, user review boards, and content aggregators.
- **Examples:** `reddit.com`, `quora.com`, `pinterest.com`, `medium.com`, `blogspot.com`, `buzzfeed.com`.
- **Handling:** Actively demoted (0.2x weighting) for factual queries. Never selected as an "official domain" in entity profiling.

---

## 3. Blacklist & Content Farm Defense

WebLens maintains an active domain denylist targeting content farms, machine-generated spam portals, and parasitic SEO mirrors:

1. **Automated Scraper Mirrors:** Domains that programmatically mirror StackOverflow, GitHub, or Wikipedia with intrusive advertising.
2. **AI-Generated Spam Portals:** Low-quality programmatic blogs generated without editorial oversight.
3. **Malware & Phishing Infrastructure:** Known hostile domains identified via community threat lists and sandbox telemetry.

---

## 4. Anti-Bot and Crawler Trap Mitigation

When indexing or extracting external websites, WebLens strictly enforces crawler defense rules:

- **Loop Detection:** Path analysis identifies recursive patterns (`/folder/folder/folder/`) and terminates crawl branches exceeding 3 duplicate segments.
- **Calendar Loop Defense:** Regular expressions identify and prune infinite calendar paths (`/\d{4}/\d{2}/\d{2}/`).
- **Query Parameter Stripping:** Session IDs, tracking tokens (`utm_source`, `fbclid`, `gclid`), and pagination parameters beyond page 5 are discarded.
- **Bandwidth Ceilings:** Single-page download limit capped at 2.0 MB; total crawl session capped at 30 pages per domain.

