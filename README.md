# Unpackr

Reliable cleanup pipeline for Usenet-style download folders.

Unpackr repairs archives, extracts video payloads, validates playback health, moves good outputs, and removes junk with explicit safety checks.

## Platform And Requirements

- Windows only
- Python 3.11+
- Required: [7-Zip](https://www.7-zip.org/)
- Strongly recommended: [par2cmdline](https://github.com/Parchive/par2cmdline), [ffmpeg](https://ffmpeg.org/)

Without ffmpeg, deep video health checks are limited.

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

## Tools

- `unpackr`: end-to-end processing pipeline
- `unpackr-doctor`: environment and dependency diagnostics
- `vhealth`: deep health checks, duplicate detection, optional delete workflows

## Documentation

- [Roadmap](ROADMAP.md)
- [Configuration](docs/CONFIGURATION.md)
- [Safety](docs/SAFETY.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Technical Notes](docs/TECHNICAL.md)
- [Changelog](docs/CHANGELOG.md)
