# Quality Gates

Use these checks before merging changes.

## Required

```powershell
py -3.13 -m ruff format --check .
py -3.13 -m ruff check .
py -3.13 -m mypy
py -3.13 -m pyright
py -3.13 -m bandit -c pyproject.toml -r core utils doctor.py unpackr.py vhealth.py
py -3.13 -m pytest -q --cov --cov-fail-under=80
```

If your default `python` already points at `3.11+`, the equivalent `python -m ...` commands are fine. On this Windows repo, `py -3.13 -m ...` is the least ambiguous invocation.

For non-Windows local smoke checks (presentation/runtime helpers only):

```bash
pytest -q tests/test_cli_render.py tests/test_runtime_helpers.py
```

To install and enforce the same gate locally:

```bash
pip install -e .[dev]
pre-commit install
pre-commit run --all-files
```

## Policy

- `ruff`: blocks syntax, correctness, import hygiene, modernization, simplification, and common bug patterns.
- `mypy`: enforces typed behavior across `core`, `utils`, and top-level entry points configured in `pyproject.toml`.
- `pyright`: provides a second fast type-analysis pass aligned with editor feedback.
- `pyright` strict tier: `core/config.py`, `core/file_handler.py`, and `core/safety_invariants.py` run under a stricter Pyright policy than the rest of the repo.
- `bandit`: scans the runtime code paths for common Python security issues.
- `pytest`: full regression suite must pass.
- Coverage: CI enforces minimum `80%` on application modules via `.coveragerc`.
- `pre-commit`: runs the same policy gate before commits.
- Presentation layer policy: interactive terminals may use Rich-based live rendering.
- Presentation layer policy: CI and non-interactive terminals must degrade safely to non-animated output paths.

Current measured state:
- full regression suite: `482` passing tests
- repo-wide coverage: `86.24%`
- notable module coverage:
  - `core/config.py`: `98%`
  - `core/file_handler.py`: `92%`
  - `core/video_processor.py`: `91%`
  - `unpackr.py`: `82%`

## Notes

- Run checks from repository root.
- `setup.py` exposes a `dev` extra for local quality tooling installs.
- Production code no longer relies on `sys.path.insert(...)` import hacks in the main processing modules.
- CLI prompt/presentation helpers now live in `utils/cli_prompts.py` instead of the `unpackr.py` entrypoint body.
- If behavior changes, add or update tests in the same change.
- For destructive-path changes (move/delete logic), regression tests are mandatory.
- CI matrix runs on Python `3.11`, `3.12`, and `3.13`.
- Linux `3.11` runs the full pre-commit quality gate.
- Windows runs the full regression suite and coverage gate.
- Linux/macOS run CLI/runtime smoke tests on every matrix lane.
