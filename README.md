# Unpackr

Reliable cleanup pipeline for Usenet-style download folders.

Unpackr repairs archives, extracts video payloads, validates playback health, moves healthy outputs, and removes junk with explicit safety controls.

## Platform And Requirements

- Windows only
- Python 3.11+
- Required: [7-Zip](https://www.7-zip.org/)
- Recommended: [par2cmdline](https://github.com/Parchive/par2cmdline), [ffmpeg](https://ffmpeg.org/)

CLI presentation (status/progress rendering) is implemented with cross-platform-safe fallbacks and is smoke-tested in CI on Windows, Linux, and macOS. Core processing workflows remain Windows-only.

Without ffmpeg, deep video health checks are limited.
Without par2, damaged archive sets cannot be repaired automatically.

Minimum supported tool versions:
- `7z`: `22.0+` (blocking if older)
- `par2`: `0.8.1+` (warning if older)
- `ffmpeg`: `4.4+` (warning if older)

## Dependency Strategy

Unpackr uses proven external tools instead of re-implementing codec, archive, or parity engines.

- Keep external engines: `7z`, `par2`, `ffmpeg`.
- Own the orchestration layer: policy, safety, retries, auditability, and tests.
- Fail clearly: `unpackr-doctor` reports missing tools and exact remediation.
- Required to run: `7z`.
- Recommended for reliability and validation depth: `par2`, `ffmpeg`.

## Quality Status

- Test suite: `380+` tests (`390` currently).
- Coverage gate: `80%` minimum in CI.
- Static checks: `ruff` + `mypy` enforced in CI.

## Install

```bash
pip install -e .
unpackr-doctor
```

Run `unpackr-doctor` first. Proceed only when blocking issues are zero.

## Quick Start

```bash
# Preview only (no file changes)
unpackr "G:\Downloads" "G:\Videos" --dry-run

# Show full pre-flight plan and exit
unpackr "G:\Downloads" "G:\Videos" --show-plan

# Live processing
unpackr "G:\Downloads" "G:\Videos"

# Optional post-run destination audit
unpackr "G:\Downloads" "G:\Videos" --vhealth
```

Equivalent named arguments are supported:

```bash
unpackr --source "G:\Downloads" --destination "G:\Videos"
```

## Operational Model

Given a source tree, Unpackr will:

1. Detect candidate processing folders.
2. Verify and optionally repair archives (PAR2 when available).
3. Extract archives (7z).
4. Validate video files (ffmpeg when available).
5. Move healthy videos to destination.
6. Remove junk and empty processed folders according to policy.
7. Preserve non-target content folders (music/images/documents) by threshold rules.

## Safety Contract

Unpackr is destructive by design. Use `--dry-run` first.

- It can delete junk, samples, corrupt videos, and empty/processed folders.
- It does not modify destination files outside normal move targets.
- It prefers fail-closed behavior: uncertain states are rejected instead of forced through.
- Cancellation (`Ctrl+C`) is handled gracefully.

Detailed policy and caveats: [docs/SAFETY.md](docs/SAFETY.md)

## Exit Behavior

- `unpackr-doctor` returns `0` when ready, `1` when blocked.
- `unpackr` returns non-zero on validation/setup/processing failures.
- `vhealth` returns non-zero on invalid input or runtime errors.

Machine-readable diagnostics: [docs/DOCTOR_JSON.md](docs/DOCTOR_JSON.md)

## Configuration

Runtime behavior is controlled by `config_files/config.json`.

Reference and examples: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## CLI Presentation

`unpackr` supports configurable terminal presentation modes:

```bash
# Auto mode (default): rich/live rendering on interactive terminals
unpackr "G:\Downloads" "G:\Videos" --animations auto

# Disable animation rendering
unpackr "G:\Downloads" "G:\Videos" --animations off

# Full mode: richer visual effects
unpackr "G:\Downloads" "G:\Videos" --animations full

# Disable ANSI colors/styles
unpackr "G:\Downloads" "G:\Videos" --no-color
```

Precedence for presentation settings:

1. CLI flags (`--animations`, `--no-color`)
2. Environment variables (`UNPACKR_ANIMATIONS`, `UNPACKR_NO_COLOR`, `NO_COLOR`)
3. Config values (`animations`, `no_color`)
4. Built-in defaults (`animations=auto`, colors enabled)

Notes:
- `UNPACKR_ANIMATIONS` accepts: `auto`, `off`, `light`, `full`.
- In CI/non-interactive terminals, advanced rendering is automatically disabled.

## Tools

- `unpackr`: end-to-end processing pipeline
- `unpackr-doctor`: environment and dependency diagnostics
- `vhealth`: deep health checks, duplicate detection, optional delete workflows

## Documentation

- [Docs Index](docs/README.md)
- [Roadmap](ROADMAP.md)
- [Configuration](docs/CONFIGURATION.md)
- [Safety](docs/SAFETY.md)
- [Quality Gates](docs/QUALITY.md)
- [CLI Presentation](docs/CLI_PRESENTATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Technical Notes](docs/TECHNICAL.md)
- [Build / Install Modes](docs/BUILD.md)
- [Changelog](docs/CHANGELOG.md)
- [Archive (historical docs)](docs/archive)
