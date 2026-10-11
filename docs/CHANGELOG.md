# Changelog

Release dates are included where recorded.

## Unreleased

- Bait releases fail safely (#12): executables, scripts, shortcuts, disguised double extensions, Unicode direction tricks and payload subtitles are removed and no video from the release is moved; archives listing such files are not extracted; `rename.bat`/`.sh` and RARBG's placeholder exe are removed without failing the release.
- Unfinished downloads are left alone (#13): releases with `.!qB`, `.!ut`, `.part`, `.crdownload` and similar files are skipped. A bare `.part` file no longer counts as a RAR part, and the duplicate-name fix only renames numeric suffixes such as `video.mkv.1` (it used to turn `x.mkv.part` and `x.mkv.exe` into `.mkv`) and never runs in a dry run.
- Samples are found across the release (#14): `Sample/`, `Proof/` and `Screens/` folders, `sample|proof|trailer|preview|promo` names with a `max_sample_duration_seconds` cap (300), a relative rule against a long main video, and `min_sample_size_mb` as the fallback when the duration is unreadable. A long video is never removed on its name alone.
- Junk coverage (#15): tracker spam names, OS cruft, verified torrent padding and empty files are removable; `VIDEO_TS`/`BDMV` releases are kept whole; `.ts` and `.m2ts` are videos by default; opt-in `dedupe_same_title` keeps only the largest encode of a title within a release.
- When the source root holds loose files, processing it no longer walks into every release folder a second time.
- First-run polish (#5): Arch/Manjaro/Omarchy install hints from `/etc/os-release` plus the no-root static `7zz` option; doctor counts each check once (tool versions fold into the tool entry), numbers its steps correctly, gives each install recipe once, and reads the par2 1.x version with `-V`; relative `log_folder` resolves under the per-user state folder instead of the current directory; a missing destination is created on live runs (and reported, not required, for `--dry-run` and `--show-plan`); `--show-plan` lists junk folders, folders kept because they hold files Unpackr never removes, and loose videos, counts 7z and zip archives, and no longer describes every folder as RAR; `.zip` and spanned zip sets are extracted; loose videos use the configured video extensions; the 10 second countdown runs only for interactive live runs; `vhealth` answers No without a terminal instead of crashing, adds `--yes`, `--no`, `--json` and `--no-color`, honors `--skip-samples` in the per-file check, reports previews as samples, lists each sample once and only animates on a terminal.
- Process conflicts: only 7-Zip, par2 or ffmpeg processes working inside the run's source are stopped, never during `--dry-run`; unrelated processes are left running.
- Removals are reversible by default. New `delete_mode` (`quarantine` default, `trash`, `permanent`) moves removed files and folders to `<source>/.unpackr-quarantine/<run_id>/` and journals every removal and move in `<source>/.unpackr-runs/<run_id>.jsonl`. New `unpackr restore <run_id>|latest` and `unpackr runs`. Quarantined runs older than `quarantine_retention_days` (14) are purged on the next live run. `--json` gains a `removal` block and per-item `disposal`; the final screen shows what is held and how to undo. `unpackr-doctor --source` reports quarantine size against `quarantine_warn_mb` (#6).
- `--json` now includes `items`, one entry per file decision with an action and reason code, plus `item_counts`; `--report FILE` writes the same items as JSON Lines with a closing summary line. Every file present before the run gets exactly one terminal action, and the dry run produces the same items marked `planned` (#7).
- The dry run treats files it plans to move, delete or extract as gone when deciding folder cleanup, so planned folder deletions match the live run.
- `--show-plan --json` includes a folder-level `plan`.
- Videos shorter than `min_video_duration_seconds` (default 10) are removed as previews or samples and counted as samples, not reported as corrupt. A missing duration is the only duration-based corruption. The dry run probes durations and lists previews as deletions instead of "validated" moves (#2).
- Truncated videos are rejected: the stream check compares how far the first video stream actually reaches with the declared duration, and recognizes ffmpeg's "File ended prematurely" and "partial file" messages (#4).
- Archive volumes are grouped into sets. A set with a missing volume, an archive 7-Zip cannot list, a password-protected archive, or an interrupted extraction is kept with its folder instead of deleted, and listing failures are no longer reported as path traversal. Only sets that extracted successfully are removed (#3).
- A live run with items needing attention exits `3` with `status: completed_with_errors`; `errors` and `warnings` carry reason codes. The dry run lists one entry per archive set and flags incomplete sets.
- Loose videos now go through the same validation, collision-safe move and guarded delete as videos in folders.

- Polished `vhealth` for multi-OS excellence: shared package version, platform-aware help, `~/` path expansion, ffmpeg preflight guidance, shared linklike scanning, and `--version`.
- Added `unpackr --json` run summaries, `docs/EXIT_CODES.md`, and a CI gate that validates `unpackr-doctor --json` schema/exit consistency.
- Added safe `--resume` via `<source>/.unpackr-state.json`, documented preservation heuristics, and aligned pre-scan thresholds to inclusive `>=` matches.
- Added preservation threshold matrix tests (music/docs inclusive edges, image count+size dual rule, video/archive priority, deletion-guard alignment).
- Added archive/video decision matrix tests (pre-scan roles, RAR/7z part selection, sample removal keywords, containment table, sample-size edges).
- Performance evidence foundation: benchmark harness `--compare` + schema v1, published Windows baseline, safety stress matrix for delete races / resume multi-writer, merge-safe `RunState` marks.
- CI Linux benchmark-harness smoke; macOS suite expanded with preservation, decision, stress, and resume tests.
- Expanded `platform_support` regression coverage (Windows/macOS tool paths, force-delete, helper detect/kill).

## v1.4.0 (2026-08-04)

First-class multi-OS release: Windows, Linux, and macOS with the same safety contract.

### Platforms
- Added PATH-first tool discovery, POSIX force-delete, and cross-platform helper process checks.
- Added POSIX launchers (`unpackr.sh`, `unpackr-doctor.sh`, `vhealth.sh`).
- Expanded CI: full Linux suite + coverage gate, expanded macOS suite, real `7z`/`ffmpeg` optional checks.
- Documented package-manager recipes and launchers in `docs/PLATFORMS.md`.

### Filesystem Hardening
- Added `utils/filesystem_policy.py` for containment, case-collision detection, symlink-farm refusal, and Unicode normalization.
- Archive path validation rejects Windows-style absolute/`..\` members on POSIX as well as Windows.
- Doctor probes case sensitivity, symlink support, and non-ASCII filename support in the working directory.
- Documented NAS permission layout plus SELinux/AppArmor troubleshooting notes.

### Performance Discipline
- Added `scripts/benchmark_harness.py` and `docs/BENCHMARKS.md` so performance changes require before/after evidence.
- Explicitly defer concurrency until safety regression evidence exists.

### Packaging / Polish
- Package version `1.4.0` with OS classifiers for Windows, Linux, and macOS.
- README mock dashboard screenshot and multi-OS install guidance.

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
