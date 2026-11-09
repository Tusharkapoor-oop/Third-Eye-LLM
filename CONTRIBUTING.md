# Contributing to WebLens

Thanks for taking the time to contribute. This repository values correctness,
security, and honest measurement over feature velocity.

## Development setup

Requirements: Python 3.11+ (CI matrix: 3.11–3.13), git.

```bash
git clone https://github.com/Tusharkapoor-oop/Third-Eye-LLM.git
cd Third-Eye-LLM

# Editable installs: the WebLens package + the root project
pip install -e ./weblens -e .
pip install pytest pytest-asyncio pytest-timeout pytest-cov respx psutil hypothesis ruff mypy bandit
```

Offline development is supported: no live provider keys are required for the
test suites. The fuzz suites run fully offline. Live-network assertions in
`tests/test_mcp_e2e.py` are gated by `WEBINTEL_LIVE_TESTS`; set it to `0` to
skip them.

## Repository layout (important)

- `weblens/src/weblens/` — **canonical** WebLens package. Edit here.
- `src/weblens/` — byte-identical mirror used by the root editable install.
  **Never edit it directly**; copy changed files from the canonical tree. The
  drift guard (`weblens/tests/test_mirror_drift.py`) fails the build otherwise.
- `tests/` — root/legacy stack tests plus cross-stack integration tests.
- `weblens/tests/` — canonical package unit/integration tests.
- `weblens-lab/`, `bench/`, `benchmarks/` — evaluation harnesses (not packaged).

## Quality gates (must pass locally before a PR)

```bash
# Lint + format
cd weblens && ruff check src tests benchmarks && ruff format --check src tests benchmarks && cd ..

# Types (canonical package, config in pyproject.toml)
mypy weblens/src/weblens

# Security static analysis (fail on medium+)
bandit -r weblens/src/weblens -ll -q

# Canonical suite with coverage (gate: >= 90%)
cd weblens && pytest tests -q --cov=weblens --cov-report=term-missing && cd ..

# Root/legacy suite
pytest tests -q --timeout=120

# Repo guards
pytest tests/test_no_tracked_secrets.py weblens/tests/test_mirror_drift.py -q
```

`pre-commit` users can install the configured hooks: `pre-commit install`.

## Coding rules

- Root-cause fixes only. No blanket `except Exception: pass`, no suppressing
  lint/type/security findings to make a gate green.
- Every behavioural change ships with a regression test that fails before the
  fix and passes after it.
- Keep the public MCP tool names, arguments, and compact output keys stable;
  document intentional changes in `docs/MCP_API_REFERENCE.md` and `CHANGELOG.md`.
- Handle all fetched web content as untrusted data. Never let it alter control
  flow or be interpreted as instructions.
- Prefer small, reviewable commits with conventional messages
  (`fix:`, `feat:`, `test:`, `docs:`, `chore:`).

## Pull request checklist

- [ ] `ruff check`, `ruff format --check`, `mypy`, `bandit -ll` pass
- [ ] Canonical suite passes with coverage ≥ 90 %
- [ ] Root suite passes (only documented environment skips)
- [ ] Drift guard and secret scan pass
- [ ] Canonical and mirror trees are byte-identical
- [ ] Docs/API reference updated for user-visible changes
- [ ] No secrets, keys, tokens, or machine-specific paths added
