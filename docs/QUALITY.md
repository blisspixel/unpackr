# Quality Gates

Use these checks before merging changes.

## Required

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pyright
python -m bandit -c pyproject.toml -r src/unpackr
python -m pytest -q --cov --cov-fail-under=80
```

Run these commands with any supported Python `3.12+` interpreter. On Windows, `py -3.15 -m ...` is an explicit alternative when `python` points elsewhere.

For non-Windows local smoke checks (presentation/runtime helpers only):

```bash
pytest -q tests/test_cli_render.py tests/test_runtime_helpers.py
```

To install and enforce the same gate locally:

```bash
python -m venv .venv && . .venv/bin/activate && python -m pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

## Policy

- `ruff`: blocks syntax, correctness, import hygiene, modernization (pyupgrade `UP` rules targeting Python 3.12), simplification, and common bug patterns.
- `mypy`: runs with `strict = true` across `src/unpackr` as configured in `pyproject.toml`. Third-party packages are checked through their stubs (`types-psutil`, `types-colorama`, `types-tqdm` in the `dev` extra).
- `pyright`: provides a second fast type-analysis pass aligned with editor feedback.
- `pyright` strict: `typeCheckingMode = "strict"` for every checked module under `src/unpackr`. No module is relaxed: there are no mypy overrides or per-file ruff `UP` ignores.
- `bandit`: scans the runtime code paths for common Python security issues.
- `pytest`: full regression suite must pass.
- Coverage: CI enforces minimum `80%` on application modules via `.coveragerc`.
- `pre-commit`: runs the same policy gate before commits.
- Presentation layer policy: interactive terminals may use Rich-based live rendering.
- Presentation layer policy: CI and non-interactive terminals must degrade safely to non-animated output paths.

Required state:
- full regression suite passes
- repo-wide coverage remains above the enforced `80%` gate
- notable module coverage from the last recorded gate:
  - `src/unpackr/core/config.py`: `98%`
  - `src/unpackr/core/file_handler.py`: `92%`
  - `src/unpackr/core/video_processor.py`: `91%`
  - `src/unpackr/cli.py`: `82%`

## Notes

- Run checks from repository root.
- `pyproject.toml` exposes a `dev` extra for local quality tooling installs.
- Production code no longer relies on `sys.path.insert(...)` import hacks in the main processing modules.
- CLI prompt/presentation helpers now live in `src/unpackr/utils/cli_prompts.py` instead of the CLI entrypoint body.
- If behavior changes, add or update tests in the same change.
- For destructive-path changes (move/delete logic), regression tests are mandatory.
- CI matrix runs on Python `3.12`, `3.13`, `3.14`, and `3.15` across Windows, Linux, and macOS.
- Every CI matrix lane launches all three installed console entry points with `--help`.
- Linux `3.12` (the oldest supported version) runs the full pre-commit quality gate.
- Windows runs the full regression suite and coverage gate.
- Linux runs the full regression suite (coverage gate on Python `3.12`) and installs `p7zip`/`par2`/`ffmpeg` for optional real-tool checks.
- macOS runs an expanded platform/safety/doctor/archive suite plus optional real-tool checks when Homebrew tools install cleanly.
- Optional tool tests live in `tests/test_external_tools_optional.py` and skip when tools are absent.
