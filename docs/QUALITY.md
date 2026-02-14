# Quality Gates

Use these checks before merging changes.

## Required

```bash
ruff check .
mypy
pytest -q --cov --cov-fail-under=55
```

## Policy

- `ruff`: blocks syntax, correctness, and common bug patterns (`E`, `F`).
- `mypy`: enforces type-checking on bootstrap/runtime helper layer configured in `pyproject.toml`.
- `pytest`: full regression suite must pass.
- Coverage: CI enforces minimum `55%` on application modules via `.coveragerc`.

## Notes

- Run checks from repository root.
- If behavior changes, add or update tests in the same change.
- For destructive-path changes (move/delete logic), regression tests are mandatory.
- CI runs the same gates on Python `3.11`, `3.12`, and `3.13`.
