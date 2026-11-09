## Summary

<!-- What changed and why. Link the issue/audit finding if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] Security hardening
- [ ] New feature
- [ ] Refactor / performance
- [ ] Documentation

## Quality checklist

- [ ] `ruff check` and `ruff format --check` pass (`weblens/`)
- [ ] `mypy weblens/src/weblens` passes
- [ ] `bandit -r weblens/src/weblens -ll` passes
- [ ] Canonical suite passes with coverage ≥ 90 %
- [ ] Root suite passes (only documented environment skips)
- [ ] Canonical and mirror trees are byte-identical (drift guard)
- [ ] Tracked-secret scan passes; no secrets or machine paths added
- [ ] Docs/API reference/changelog updated for user-visible changes
- [ ] Behavioural changes include a regression test that fails without the fix

## Verification

<!-- Paste the commands you ran and their result summary. -->
