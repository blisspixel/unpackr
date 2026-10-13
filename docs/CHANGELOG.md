# Changelog

Release dates are included where recorded.

## Unreleased

- Install with `uv tool install .` or `pipx install .`. A system `python -m pip install .` is refused on externally managed Pythons (Arch, Debian, Ubuntu). Use `python -m pip install .` only inside a virtualenv.
- The installable distribution is one `unpackr` package. Imports live under `unpackr` rather than top-level `core`, `utils`, `doctor`, or `vhealth`.
- Unknown config keys print a warning and still load. `settle_minutes` and `notify` are reported as no longer used.

## v1.6.1 (2026-10-11)

Found by running Unpackr on a realistic messy downloads folder.

- **Photos and music are kept, however few.** A folder without videos was only kept with 10+ music files, or 10+ images totalling over 10 MB, so a small photo folder or a 3-track single was deleted as junk. Any music, photos or documents now keep the folder (`min_music_files`, `min_image_files` and `min_documents` default to `1`; raise them to clean up stray pictures). Inside a video release, fewer than 10 images or 10 MB is still cover art and goes with the release.
- The dry run lists the junk folders it will delete under CLEANUP (it used to show only processed folders, hiding exactly the ones worth checking) and applies the same "is it really removable" check as the live run.
- The dry run no longer plans an obfuscated post's randomly named volumes as junk: PAR2 may rename them back during the live run, so they are shown as `par2_rename_pending`.
- Loose videos in the source folder are processed once, not twice, and `videos_found` no longer counts every video in the tree twice.

## v1.6.0 (2026-10-11)

Unpackr is a tool you run by hand when you are ready to clean, not something to schedule.

- Removed the timer/service mode: `unpackr service install|status|uninstall`, `--unattended`, `--notify`, the `settle_minutes` and `notify` settings, desktop notifications and the `skipped` run status. Every run follows the same rule: unfinished downloads and archives that cannot be unpacked are junk.
- Kept the per-source run lock: a second run started on the same folder exits with `run_locked` (exit `1`) instead of racing the first.

**Upgrade notes**
- If you installed the service, remove it first with 1.5.x (`unpackr service uninstall --all`), or delete `~/.config/systemd/user/unpackr-*` and run `systemctl --user daemon-reload`.
- `settle_minutes` and `notify` in a config file are no longer used. Current builds warn and keep loading the rest of the file.

## v1.5.1 (2026-10-11)

- On a manual run, an archive set that cannot be unpacked is junk: a set with a volume missing that PAR2 could not rebuild, one cut short, one 7-Zip cannot read, or a password-protected one is removed (to quarantine by default) and listed under DAMAGED, RE-DOWNLOAD and in `--json` `damaged`, instead of being kept and making the run exit `3`. Sets held back by the machine (disk full, extraction timeout, 7-Zip missing or failing) are still kept, and unattended runs keep every such set for a later run. Archives with CRC errors are now removed explicitly too, so leftovers in the source root no longer linger.

## v1.5.0 (2026-10-11)

Unpackr cleans a downloads folder decisively and never throws away the good file. Removals are reversible by default, every decision is reported, PAR2 repairs obfuscated posts, and the code base is strictly typed on Python 3.12 to 3.15.

**Upgrade notes**
- Python 3.12 or newer is required (3.11 is dropped). Reinstall with `uv tool install .` (or `pipx install .`).
- 7-Zip 22.0+ is required: on macOS use `brew install sevenzip`, on Debian/Ubuntu/Fedora the `7zip` package (the old `p7zip` 16.02 is too old).
- Removals now go to `<source>/.unpackr-quarantine/` for 14 days by default; set `delete_mode` to `trash` or `permanent` for the old behavior.
- A manual run removes unfinished downloads as junk; unattended runs wait for them.
- `--json` writes only JSON to stdout; human output moved to stderr.


- PAR2 never removes archive volumes (#21). par2 is given every file in the folder (`par2 r <set>.par2 *`), so obfuscated posts with renamed volumes are matched, renamed back and extracted instead of being discarded as "damaged beyond repair". Every PAR2 set in a folder is checked, not just the first. Whatever PAR2 reports, extraction still runs and 7-Zip's CRC check decides; `.par2` files are removed only with a set that extracted. A release PAR2 says is damaged beyond repair (nothing extractable) is junk and listed for re-download; one par2 could not judge (tool error, par2 not installed) next to unrecognized files is kept and needs attention. Without par2 installed, archives still extract.
- Archive removal is guarded in depth (#21): removals pass a truthful `extraction_verified`, invariant I3 recognises split volumes (`.r00`, `.7z.001`, `.z01`, `.001`) and is wired into CLI runs, and the archive step refuses to remove anything without a configured remover instead of falling back to a permanent unlink.
- A manual run means "clean now" (#21): it does not wait for `settle_minutes`; that wait (and skipping releases that are still downloading) applies to unattended runs, which now count them in `counts.folders_settling`, show them on the summary screen and in the notification, and no longer delete a fresh junk-only folder that is still being written.
- Damaged downloads are listed (#21): corrupt or truncated videos, archives with CRC errors and releases PAR2 cannot repair appear under DAMAGED, RE-DOWNLOAD on the summary screen, in the notification and in the new `damaged` list in `--json`.
- The dry run runs the same read-only archive checks as the live run (missing volume, listing, password, unsafe contents), so it keeps and blocks the same sets and plans the same folder deletions (#21).
- 7-Zip runs with `-p-`: password-protected archives, including ones with encrypted headers, fail at once as `archive_password` instead of waiting at a prompt or reporting `archive_unlistable` (#21).
- `--json` stdout carries only the JSON summary; the banner, progress and summary screen go to stderr, so `unpackr --json | jq` works.
- The bundled `config_files/config.json` lists `.ts` and `.m2ts` as videos, matching the documented defaults (#21).
- Notifications count extracted archives again (they read a counter that did not exist).
- `unpackr-doctor` explains what a missing par2 means: damaged or renamed volumes cannot be repaired, archives still extract.
- Python 3.12 is now the minimum and 3.15 is supported; CI runs 3.12 through 3.15. **Migration:** Python 3.11 is no longer supported. Install a 3.12+ interpreter and reinstall (`uv tool install .` or `pipx install .`); `unpackr-doctor` reports an older interpreter as a blocking issue.
- Type checking is strict: `mypy --strict` and Pyright strict cover `core`, `utils`, `doctor.py`, `unpackr.py` and `vhealth.py` with no per-module relaxations, ruff applies the pyupgrade (`UP`) rules for 3.12, and the `dev` extra installs stubs for psutil, colorama and tqdm.
- Pressing Ctrl+C just after the app is created (before the run starts) exits cleanly as cancelled instead of crashing with `UnboundLocalError`.
- Malformed state files no longer crash or stop a run: a run journal line, service manifest, event log record or cached environment profile that is valid JSON but not an object is skipped (an event log record with unknown fields no longer stops the rest of the log from loading), and a configured tool path that exists but cannot be executed is skipped instead of raising.
- POSIX force-delete uses `shutil.rmtree(onexc=...)` instead of the deprecated `onerror`.

- Unattended runs (#9): `unpackr service install|status|uninstall` manages a systemd user timer (and a `.path` unit with `--on-change`), shows the units and asks before enabling them, and removes exactly what it wrote. `--unattended` turns off animation, the countdown and prompts, prints one line per folder, takes a per-source lock so overlapping runs exit cleanly, and skips downloads changed within `settle_minutes`. `--notify` (or `notify: true`) sends one desktop notification for runs that did something. Live runs on the same source can no longer overlap, and progress output has no cursor redraws when stdout is not a terminal. A six-folder unattended run takes about 0.7 s.
- Output naming (#8): `output_layout` with `flat`, `release`, `movies`, `tv` and `auto` presets or a custom template, using a local release-name parser (episodes, multi-episode, `1x02`, years inside titles). Obfuscated video names take the release folder name (`deobfuscate_names`), subtitles move with their video under a matching name (`keep_subtitles`), and the dry run shows each video's final destination.
- A timing-sensitive adaptive-policy test no longer compares disk benchmark classifications between runs.
- Bait releases fail safely (#12): executables, scripts, shortcuts, disguised double extensions, Unicode direction tricks and payload subtitles are removed and no video from the release is moved; archives listing such files are not extracted; `rename.bat`/`.sh` and RARBG's placeholder exe are removed without failing the release.
- Unfinished downloads (#13): on a manual run, `.!qB`, `.!ut`, `.part`, `.crdownload` and similar files are junk and removed (`download_incomplete`) while the finished files of the release are processed; unattended runs skip those releases (`download_in_progress`) until they finish. A bare `.part` file no longer counts as a RAR part, and the duplicate-name fix only renames numeric suffixes such as `video.mkv.1` (it used to turn `x.mkv.part` and `x.mkv.exe` into `.mkv`) and never runs in a dry run.
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
