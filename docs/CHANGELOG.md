# Changelog

Release dates are included where recorded.

## Unreleased

- None.

## v1.3.1 (2026-08-02)

Reliability, packaging, and operator-safety release for the `1.3.x` line.

### Packaging And Install
- Fixed package metadata so fresh installs include the `unpackr`, `unpackr-doctor`, and `vhealth` command modules plus bundled configuration files.
- Prevented ignored local `comments.json` customizations from leaking into built wheels.
- Made the default config path independent of the current working directory.
- Restored a repository `LICENSE` matching Apache 2.0 + Commons Clause packaging metadata.
- Added an installed CLI smoke check and wheel-contents smoke check to CI.
- Added Python 3.14 to CI and package metadata, and updated GitHub Actions runtimes.

### CLI And Configuration
- Made incomplete or conflicting source/destination arguments fail with a clear usage error instead of silently entering interactive mode.
- Made explicit `--config` paths fail early when the file does not exist and added matching config support to `unpackr-doctor`.
- Made invalid or unreadable configuration block `unpackr` and `vhealth` instead of continuing with fallback settings.
- Clarified invalid-config messaging so it no longer claims defaults will be used when startup is blocked.
- Wired documented retry and archive-loop settings into runtime properties and removed four inert default keys.
- Accepted the common `--destinantion` misspelling as a hidden compatibility alias while keeping `--destination` canonical.
- Rejected empty or null-byte `log_folder` values during config validation.

### Safety And Security
- Hardened `SystemCheck` so malformed `tool_paths` values cannot crash tool discovery.
- Aligned default safety-limit constants with the documented runtime defaults.
- Corrected safety documentation for recursion depth and global runtime limits.
- Restricted CI workflow token permissions to `contents: read`.
- Bounded captured subprocess output for temp-file archive operations.
- Fixed `InputValidator.validate_path(base_dir=...)` to raise when a path escapes the trusted base directory.
- Hardened atomic file moves so a failed final rename restores the source instead of deleting the temporary move file.
- Changed disk-space check failures to fail closed instead of assuming enough free space.
- Restricted locked-folder process termination to known helper processes and true child paths.

### Quality And Docs
- Raised and enforced the quality gate through local `pre-commit` and CI.
- Corrected the sample-threshold documentation, which previously recommended a value that would delete more small videos.
- Refreshed core docs (`README`, `ROADMAP`, `TECHNICAL`, `BUILD`, `TROUBLESHOOTING`, `SAFETY`) for current behavior.
- Updated docs to use interpreter-neutral `python -m ...` quality commands.

## v1.3.0 (2026-01-07)

- Graceful cancellation: `Ctrl+C` exits within 5 seconds.
- Terminates running `7z`/`par2`/`ffmpeg` processes on cancel.
- Shows `cancelled` status in summary with partial stats.
- Second `Ctrl+C` forces immediate exit.
- `vhealth`: fixed double-deletion bug.
- `vhealth`: cleaner progress display (single line).
- `vhealth`: suppressed noisy log messages during progress.
- `vhealth`: keeps files with `fav` prefix when duplicates are found.

## v1.2.2 (2026-01-07)

- Progress display shows `calculating...` instead of `0.0` during warmup.
- Fixed structured events module to handle non-existent files gracefully.
- Fixed success rate calculation to use terminal states only.
- Removed broken chaos tests.
- Simplified roadmap to match project philosophy.

## v1.2.1

- Modern progress display with live stats.
- Rarity-based comment system.
- Improved filename sanitization (Cyrillic/Unicode transliteration).
- Non-recursive video scanning for faster UI updates.
- UTF-8 console support on Windows.

## v1.2.0

- Fast folder scanning with `os.scandir` (2 to 3x faster).
- Dynamic timeouts based on file size (handles 50GB+ archives).

## v1.1.0

### Security
- Path traversal protection (validates archive contents before extraction)
- Command injection prevention (safe subprocess handling)
- Buffer overflow protection (temp files for large operations)

### Stability
- Exception handler cleanup (proper spinner thread cleanup)
- Memory leak fix (bounded deque for failure tracking)
- Race condition fix (double-check before deletion)
- Comprehensive config validation

## v1.0.0

- Initial release.
- PAR2 repair and verification.
- RAR/7z extraction.
- Video health validation.
- Junk file cleanup.
- Content folder preservation.
- Comprehensive logging.
- 33 tests.
