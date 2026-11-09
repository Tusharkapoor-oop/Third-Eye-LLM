# WebLens Developer Guide

## 0. Quality gates (read this first)

Every change must keep these green (also enforced in CI and via `pre-commit`):

```bash
cd weblens
ruff check src tests benchmarks
ruff format --check src tests benchmarks
mypy src/weblens                      # 0 errors
bandit -r src/weblens -ll -q          # no medium/high
pytest tests --cov=weblens            # all pass, coverage >= 90 %
cd ..
pytest tests --timeout=120            # root/legacy suite, no hangs
pytest weblens/tests/test_mirror_drift.py tests/test_no_tracked_secrets.py -q
```

`weblens/src/weblens` is canonical; `src/weblens` is a byte-identical mirror.
Never edit the mirror directly — the drift guard fails the build. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for the full workflow.

## 1. Environment Setup & Prerequisites
WebLens requires Python 3.11 or later.

### 1.1 Virtual Environment Installation
```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install core dependencies
pip install -e weblens/
```

### 1.2 Configuration (`.env`)
Create a git-ignored `.env` file in the project root:
```ini
# Optional commercial provider keys
BRAVE_API_KEY=your_brave_key_here
TAVILY_API_KEY=your_tavily_key_here

# Local engine endpoints
SEARXNG_BASE_URL=http://localhost:8080

# Logging and security
WEBLENS_LOG_LEVEL=INFO
WEBLENS_ALLOW_BROWSER=false
```

---

## 2. CLI Usage

The WebLens CLI provides direct access to core retrieval and application features:

```powershell
# Run a quick web search
python -m weblens.cli search "python asyncio tutorial" --max-results 3

# Extract content from a specific URL with query-focused passage scoring
python -m weblens.cli extract https://docs.python.org/3/library/asyncio.html --query "Event loop"

# Map a website's structure
python -m weblens.cli crawl https://example.com --mode map --max-pages 10

# Execute deep research
python -m weblens.cli research "comparison of SQLite vs DuckDB for local analytics"

# Run system diagnostics
python -m weblens.cli doctor
```

---

## 3. Running Verification & Test Suites

```powershell
# Run weblens core unit tests
python -m pytest weblens/tests -v

# Run root evaluation and integration test suite
python -m pytest tests/ -v

# Verify cryptographic evidence ledger and artifact digests
python tools/verify_evidence.py

# Rebuild deterministic evaluation report
python tools/build_report.py

# Lint report for zero untraceable numbers and 100% metric provenance
python tools/lint_report.py
```

