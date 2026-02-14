# Quality Gates

Use these checks before merging changes.

## Required

```bash
ruff check .
python -m mypy
pytest -q --cov --cov-fail-under=80
```

For non-Windows local smoke checks (presentation/runtime helpers only):

```bash
pytest -q tests/test_cli_render.py tests/test_runtime_helpers.py
```

## Policy

- `ruff`: blocks syntax, correctness, and common bug patterns (`E`, `F`).
- `mypy`: enforces type-checking on bootstrap/runtime helper layer configured in `pyproject.toml`.
- `pytest`: full regression suite must pass.
- Coverage: CI enforces minimum `80%` on application modules via `.coveragerc`.
- Presentation layer policy:
  - Interactive terminals may use Rich-based live rendering.
  - CI/non-interactive terminals must degrade safely to non-animated output paths.

## Notes

- Run checks from repository root.
- If behavior changes, add or update tests in the same change.
- For destructive-path changes (move/delete logic), regression tests are mandatory.
- CI matrix runs on Python `3.11`, `3.12`, and `3.13` across:
  - Windows: full test suite + coverage gate.
  - Linux/macOS: static checks + CLI/runtime smoke tests.
