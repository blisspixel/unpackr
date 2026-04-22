# Technical Notes

Implementation-oriented details for maintainers.

## Architecture

```text
unpackr/
|-- unpackr.py               # Main CLI orchestration
|-- doctor.py                # Environment and dependency diagnostics
|-- vhealth.py               # Destination video audit tool
|-- core/
|   |-- archive_processor.py
|   |-- config.py
|   |-- file_handler.py
|   |-- logger.py
|   |-- safety_invariants.py
|   |-- structured_events.py
|   `-- video_processor.py
|-- utils/
|   |-- cli_render.py
|   |-- cli_prompts.py
|   |-- cli_runtime.py
|   |-- defensive.py
|   |-- dry_run_summary.py
|   |-- error_messages.py
|   |-- progress.py
|   |-- safety.py
|   `-- system_check.py
`-- tests/
```

## External Tool Boundary

Unpackr intentionally delegates archive/parity/media engine work to mature external tools.

- Required runtime tool: `7z` (`22.0+`, blocking if missing/too old)
- Recommended runtime tool: `par2` (`0.8.1+`, warning if missing/too old)
- Recommended runtime tool: `ffmpeg` (`4.4+`, warning if missing/too old)

Why:
- Lower defect surface for complex binary formats
- Better compatibility/performance than custom re-implementation
- Reliability work stays focused on orchestration and policy

## Processing Flow

1. Pre-scan source tree and classify folders.
2. Process candidate folders:
   - PAR2 verify/repair
   - archive extraction
   - video validation
   - move healthy outputs
   - cleanup/removal with safety guards
3. Retry locked-folder deletions.
4. Final empty-folder cleanup pass.
5. Optional `vhealth` destination audit.

## Safety Model

- Fail-closed behavior for uncertain destructive operations
- Path and input validation before I/O operations
- Recursion/loop/runtime guards (`utils/safety.py`)
- Retry + backoff for transient lock/permission failures
- Dry-run parity: decision logic is shared with live mode

## Quality Model

- CI quality gates:
  - `py -3.13 -m ruff format --check .`
  - `py -3.13 -m ruff check .`
  - `py -3.13 -m mypy`
  - `py -3.13 -m pyright`
  - `py -3.13 -m bandit -c pyproject.toml -r core utils doctor.py unpackr.py vhealth.py`
  - `py -3.13 -m pytest -q --cov --cov-fail-under=80`
- Tests are branch-focused on destructive-path safety and recovery behavior.
- `core/config.py`, `core/file_handler.py`, and `core/safety_invariants.py` are held to a stricter Pyright tier than the rest of the codebase.
- Production modules use package imports directly rather than runtime `sys.path` mutation.
- `unpackr.py` keeps orchestration responsibilities; prompt/presentation helper functions were extracted into `utils/cli_prompts.py`.
- Current quality snapshot is `482` passing tests and `86.24%` total coverage.

## Developer Commands

```powershell
py -3.13 -m ruff format --check .
py -3.13 -m ruff check .
py -3.13 -m mypy
py -3.13 -m pyright
py -3.13 -m bandit -c pyproject.toml -r core utils doctor.py unpackr.py vhealth.py
py -3.13 -m pytest -q --cov --cov-fail-under=80
```
