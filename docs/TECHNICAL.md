# Technical Notes

Implementation-oriented details for maintainers.

## Architecture

```text
unpackr/
├── unpackr.py               # Main CLI orchestration
├── doctor.py                # Environment and dependency diagnostics
├── vhealth.py               # Destination video audit tool
├── core/
│   ├── archive_processor.py
│   ├── config.py
│   ├── file_handler.py
│   ├── logger.py
│   ├── safety_invariants.py
│   ├── structured_events.py
│   └── video_processor.py
├── utils/
│   ├── cli_runtime.py
│   ├── defensive.py
│   ├── dry_run_summary.py
│   ├── error_messages.py
│   ├── progress.py
│   ├── safety.py
│   └── system_check.py
└── tests/
```

## External Tool Boundary

Unpackr intentionally delegates archive/parity/media engine work to mature external tools.

- Required runtime tool: `7z` (`22.0+`, blocking if missing/too old)
- Recommended runtime tools:
  - `par2` (`0.8.1+`, warning if missing/too old)
  - `ffmpeg` (`4.4+`, warning if missing/too old)

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
  - `ruff check .`
  - `mypy`
  - `pytest --cov --cov-fail-under=80`
- Tests are branch-focused on destructive-path safety and recovery behavior.

## Developer Commands

```bash
ruff check .
mypy
pytest -q --cov --cov-fail-under=80
```
