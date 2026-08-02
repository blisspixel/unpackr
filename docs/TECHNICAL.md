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
|   |-- platform_support.py
|   |-- progress.py
|   |-- safety.py
|   `-- system_check.py
`-- tests/
```

## External Tool Boundary

Unpackr intentionally delegates archive/parity/media engine work to mature external tools.

- Required runtime tool: `7z` / `7zz` (`22.0+`, blocking if missing/too old)
- Recommended runtime tool: `par2` (`0.8.1+`, warning if missing/too old)
- Recommended runtime tool: `ffmpeg` (`4.4+`, warning if missing/too old)

Why:
- Lower defect surface for complex binary formats
- Better compatibility/performance than custom re-implementation
- Reliability work stays focused on orchestration and policy

## Platform Support

- Supported OS targets: Windows, Linux, macOS
- Shared policy lives in `utils/platform_support.py`:
  - PATH-first tool candidate lists (plus Windows absolute fallbacks / Homebrew prefixes)
  - helper-process detection and termination
  - force-delete fallbacks (encoded PowerShell on Windows; guarded `rmtree` on POSIX)
- Filename sanitization remains conservative so outputs stay portable across filesystems
- CLI presentation already degrades safely on non-Windows terminals (`docs/CLI_PRESENTATION.md`)

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
  - `python -m ruff format --check .`
  - `python -m ruff check .`
  - `python -m mypy`
  - `python -m pyright`
  - `python -m bandit -c pyproject.toml -r core utils doctor.py unpackr.py vhealth.py`
  - `python -m pytest -q --cov --cov-fail-under=80`
- Tests are branch-focused on destructive-path safety and recovery behavior.
- `core/config.py`, `core/file_handler.py`, and `core/safety_invariants.py` are held to a stricter Pyright tier than the rest of the codebase.
- Production modules use package imports directly rather than runtime `sys.path` mutation.
- `unpackr.py` keeps orchestration responsibilities; prompt/presentation helper functions were extracted into `utils/cli_prompts.py`.
- The full regression suite passes above the enforced `80%` coverage gate.
- CI matrix: Windows/Linux/macOS x Python `3.11`–`3.14`, with installed entry-point smoke checks on every lane.

## Developer Commands

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pyright
python -m bandit -c pyproject.toml -r core utils doctor.py unpackr.py vhealth.py
python -m pytest -q --cov --cov-fail-under=80
```
