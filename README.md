# Unpackr

Unpackr is a Windows automation tool for cleaning and processing Usenet-style download folders with a reliability-first workflow.

## Why Unpackr

- Reduces manual cleanup: verify, extract, validate, move, and clean in one run.
- Prioritizes safety: fail-closed behavior, preflight checks, and dry-run support.
- Designed for operations: clear exit codes, diagnostics, and CI-tested behavior.

## Requirements

- Windows
- Python `3.11+`
- Required: [7-Zip](https://www.7-zip.org/)
- Recommended: [par2cmdline](https://github.com/Parchive/par2cmdline), [ffmpeg](https://ffmpeg.org/)

Minimum supported versions:
- `7z`: `22.0+` (required)
- `par2`: `0.8.1+` (recommended)
- `ffmpeg`: `4.4+` (recommended)

## Install

```bash
pip install -e .
unpackr-doctor
```

Run `unpackr-doctor` before live processing and resolve blocking issues first.

## Quick Start

```bash
# Preview only (no file changes)
unpackr "G:\Downloads" "G:\Videos" --dry-run

# Show plan and exit
unpackr "G:\Downloads" "G:\Videos" --show-plan

# Live run
unpackr "G:\Downloads" "G:\Videos"
```

Named arguments are also supported:

```bash
unpackr --source "G:\Downloads" --destination "G:\Videos"
```

## Safety

Unpackr performs destructive actions when running live. Use `--dry-run` first.

- Can delete junk, samples, corrupt videos, and empty processed folders.
- Uses conservative decision rules when state is uncertain.
- Handles cancellation (`Ctrl+C`) with guarded shutdown behavior.

Policy details and limits: [docs/SAFETY.md](docs/SAFETY.md)

## Legal Notice

Recording, retention, and monitoring requirements (including one-party/two-party consent rules) vary by jurisdiction and context.

You are responsible for complying with applicable laws, contracts, and organizational policies. This project does not provide legal advice.

## Tooling And Exit Codes

- `unpackr`: processing pipeline
- `unpackr-doctor`: environment and dependency checks
- `vhealth`: post-run video health checks

Exit semantics:
- `unpackr-doctor`: `0` ready, `1` blocked
- `unpackr`: non-zero on validation/setup/processing failures
- `vhealth`: non-zero on invalid input/runtime errors

Doctor JSON output: [docs/DOCTOR_JSON.md](docs/DOCTOR_JSON.md)

## Documentation

Detailed documentation is in [`docs/`](docs/README.md).

- [Docs Index](docs/README.md)
- [Roadmap](ROADMAP.md)
- [Configuration](docs/CONFIGURATION.md)
- [Safety](docs/SAFETY.md)
- [CLI Presentation](docs/CLI_PRESENTATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Technical Notes](docs/TECHNICAL.md)
