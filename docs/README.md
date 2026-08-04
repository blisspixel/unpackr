# Documentation

This directory contains the authoritative documentation for current supported behavior.
Use this index to find the right doc for operations, troubleshooting, and maintenance work.

## Start Here

- `../README.md` - product overview and quick start
- `../ROADMAP.md` - current priorities and milestone status

## Operations And Policy

- `SAFETY.md` - destructive-operation safety contract
- `CONFIGURATION.md` - `config_files/config.json` reference
- `PLATFORMS.md` - Windows / Linux / macOS install, launchers, filesystem/NAS/SELinux notes
- `BENCHMARKS.md` - micro-benchmark harness and performance evidence rules
- `TROUBLESHOOTING.md` - common failures and remediation
- `DOCTOR_JSON.md` - `unpackr-doctor --json` schema/contract
- `EXIT_CODES.md` - exit codes and machine-readable run output

## Engineering And Release

- `QUALITY.md` - quality gates and enforcement
- `TECHNICAL.md` - implementation notes for maintainers
- `CLI_PRESENTATION.md` - terminal rendering modes and fallback behavior
- `BUILD.md` - install/build modes
- `CHANGELOG.md` - user-visible changes by release

Quality contract:
- full suite required to pass
- coverage required to remain at or above `80%`
- stricter typed modules: `core/config.py`, `core/file_handler.py`, `core/safety_invariants.py`
- supported OS targets: Windows, Linux, macOS (see `ROADMAP.md` for the cross-platform milestone)

## Archive

- `archive/` contains historical or superseded documents kept for context.
- Archive content is non-authoritative unless explicitly re-promoted.
