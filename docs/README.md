# Documentation

This directory contains the authoritative documentation for current supported behavior.
Use this index to find the right doc for operations, troubleshooting, and maintenance work.

## Start Here

- `../README.md` - product overview and quick start
- `../ROADMAP.md` - current priorities and milestone status

## Operations And Policy

- `SAFETY.md` - destructive-operation safety contract
- `CONFIGURATION.md` - `config_files/config.json` reference
- `TROUBLESHOOTING.md` - common failures and remediation
- `DOCTOR_JSON.md` - `unpackr-doctor --json` schema/contract

## Engineering And Release

- `QUALITY.md` - quality gates and enforcement
- `TECHNICAL.md` - implementation notes for maintainers
- `CLI_PRESENTATION.md` - terminal rendering modes and fallback behavior
- `BUILD.md` - install/build modes
- `CHANGELOG.md` - user-visible changes by release

Current quality snapshot:
- full suite: `482` passing tests
- coverage: `86.24%`
- stricter typed modules: `core/config.py`, `core/file_handler.py`, `core/safety_invariants.py`

## Archive

- `archive/` contains historical or superseded documents kept for context.
- Archive content is non-authoritative unless explicitly re-promoted.
