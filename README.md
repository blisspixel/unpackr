# Unpackr

Unpackr is a Windows automation tool for processing Usenet-style download folders with safety-first, predictable behavior.

## Why Unpackr

- Reduces manual cleanup: verify, extract, validate, move, and clean in one run.
- Keeps risky operations explicit: fail-closed behavior, preflight checks, and dry-run support.
- Built for operators: clear exit codes, diagnostics, and CI-tested behavior.

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

## Legal And Compliance Notice

Only use Unpackr on files you are allowed to handle.

You are responsible for following the laws, licenses, and rules that apply to your setup (including copyright, privacy, and retention requirements).

Unpackr can move and delete files. Run `--dry-run` first and review the plan before live use.

This project is a technical tool, not legal advice, and is provided "as is." See `LICENSE` for full terms.

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
- [Quality Gates](docs/QUALITY.md)
- [Build And Install](docs/BUILD.md)
- [Changelog](docs/CHANGELOG.md)
