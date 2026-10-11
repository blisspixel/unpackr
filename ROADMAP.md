# Roadmap

Unpackr turns a messy downloads folder into a clean one: it keeps the good content and deletes the rest. This roadmap is reliability-first: never lose the good file, then correctness, cross-platform parity, observability, then performance.

## Version Focus

- Current line: `1.5.x` (latest: `1.5.1`, October 2026) — first-class **Windows, Linux, and macOS**, Python `3.12` to `3.15`
- Primary objective: delete the junk decisively, never the good file, and make every removal reversible and explained

## Quality Baseline

- CI quality gate is `80%` coverage minimum.
- The full regression suite must pass before merge.
- Dependency/version policy is enforced by `unpackr-doctor` and runtime preflight.
- Installed CLI entry points and documented path flags are covered by regression and CI smoke tests.
- Python support floor is `3.12+` (CI matrix includes `3.12` through `3.15`).
- Active documentation stays under `docs/`; superseded content belongs in `docs/archive/`.
- Platform policy lives in `utils/platform_support.py` rather than ad-hoc `sys.platform` checks.

## Guiding Principles

- Deleting junk is the job. Safeguards protect the good content (videos, music, photos, documents, a release that could still be repaired), not the junk.
- When the content might be good and Unpackr cannot tell, keep it and say why (fail closed on the good file).
- A manual run means "clean now"; only unattended runs wait for downloads to finish.
- Every removal is reversible by default (quarantine) and explained (reason codes, `--json`, the summary screen).
- Ship measurable reliability gains each iteration.
- Prefer explicit policy over implicit behavior.
- Prefer PATH-resolved tools first; platform-specific absolute paths are fallbacks only.
- Windows remains a first-class target; Linux and macOS must reach the same safety bar, not a degraded subset.

## Research Summary (Cross-Platform)

Unpackr is already mostly portable:

| Layer | Status | Notes |
|-------|--------|-------|
| Python orchestration | Portable | `pathlib`, list-form subprocess, config/JSON |
| External tools | Portable | `7z` / `7zz`, `par2`, `ffmpeg` via package managers |
| Safety invariants | Portable | path containment, symlink refusal, dry-run parity |
| Process lock handling | Portable core | `psutil` open-file checks work on POSIX |
| Force-delete fallback | Was Windows-only | PowerShell path; POSIX now uses guarded `rmtree` |
| Defaults / docs / CI | Were Windows-centric | PATH-first defaults + expanded non-Windows CI |

Main historical friction was product framing and defaults (Windows paths, PowerShell-only fallbacks, doctor process checks skipped on non-Windows, Linux/macOS CI limited to smoke tests)—not an architectural hard block.

## Milestones

### Done: Cross-Platform Foundations (`1.4.0`)

Goal: make Linux and macOS supported platforms with the same safety contract as Windows.

Status:
- Complete in `1.4.0` (platform helpers, PATH-first tools, multi-OS docs/CI).

### Done: Cross-Platform Parity Hardening (`1.4.x`)

Goal: make Linux/macOS behavior as boringly reliable as Windows for real operator workloads.

Status:
- Complete in `1.4.0` (full Linux suite, expanded macOS suite, real-tool checks, POSIX launchers, filesystem quirk policy/docs).

### Done: Observability And Automation

Goal: make runtime behavior machine-verifiable in CI and local scripts.

Acceptance criteria:
- CI can block on doctor output and explicit issue counts.
- Exit semantics are documented and covered by tests.
- Structured outputs include timestamps, status, and actionable remediation hints.

Status:
- Complete for 1.4.x automation contracts: doctor JSON + CI gate; unpackr `--json`; `docs/EXIT_CODES.md`. Optional follow-up: per-folder structured event streams.

### Done: Correctness And Recovery Hardening

Goal: reduce false positives/false negatives in processing decisions.

Acceptance criteria:
- Interrupted runs are resumable without duplicate moves or unsafe deletes.
- Archive/video decision paths are reproducibly testable.
- Preservation heuristics have documented limits and examples.

Status:
- Complete for 1.4.x correctness contracts: `--resume` + `.unpackr-state.json`; `docs/PRESERVATION.md`; pre-scan inclusive thresholds (`tests/test_preservation_thresholds.py`); archive/video decision matrices (`tests/test_decision_matrix.py`); deletion-guard alignment.

### Done: Performance With Evidence (foundation)

Goal: improve throughput without regressing safety.

Acceptance criteria:
- Benchmark results published with hardware profile details.
- Performance changes must include before/after evidence.
- No safety invariant regressions in stress tests.

Status:
- Complete for evidence infrastructure: harness schema v1 + `--compare`; published sample baseline (`benchmarks/published/`); safety stress matrix (`tests/test_safety_stress_matrix.py`); resume-state merge-safe multi-writer hardening. **Concurrency remains deferred** until a real multi-archive workload is measured with and without parallelism.

### Done: Clean Downloads, Safely (`1.5.0`)

Goal: make Unpackr the tool you point at a downloads folder and trust: decisive about junk, careful with the good file.

Status:
- Complete in `1.5.0`: reversible removals (quarantine, trash, `unpackr restore`); a decision for every file in `--json`/`--report`; previews, truncated videos and incomplete archive sets handled correctly; bait, junk, samples and unfinished downloads screened; output layouts and name deobfuscation; unattended mode with a systemd user service; PAR2 that repairs obfuscated posts and never removes unextracted volumes; dry-run/live parity; strict typing (`mypy --strict`, Pyright strict) on Python 3.12 to 3.15.

### Next

- Real-tool CI on Windows (7-Zip, par2 and ffmpeg are installed on Linux and macOS runners only).
- Unattended runs on macOS (launchd) and Windows (Task Scheduler) with the same `service install` experience as systemd.
- Concurrency stays deferred until a real multi-archive workload is measured with and without it.

## Cross-Platform Implementation Plan

### Phase A — Foundations
1. Introduce `utils/platform_support.py` for OS detection, tool candidates, process helpers, force-delete.
2. Route `SystemCheck`, `doctor`, and `FileHandler` through those helpers.
3. Make default `tool_paths` PATH-first and multi-OS aware.
4. Expand Linux CI beyond smoke tests.
5. Rewrite product docs to stop saying “Windows-only.”

Status: done.

### Phase B — Parity
1. Run the full suite on Linux CI; widen macOS coverage.
2. Add package-manager install docs and doctor remediation text per OS.
3. Validate real archive extraction/video health on non-Windows runners when tools are present.
4. Add POSIX launcher scripts and packaging notes.

Status: done in `1.4.0`.

### Phase C — Exceptional polish
1. Filesystem quirk matrix and tests (case sensitivity, symlink farms, non-ASCII paths).
2. Permission model notes for multi-user NAS layouts.
3. Optional SELinux/AppArmor troubleshooting notes if operators hit confinement issues.
4. Benchmark evidence per OS before any concurrency work.

Status: done in `1.4.0` (`utils/filesystem_policy.py`, doctor FS probe, `docs/PLATFORMS.md`, `docs/BENCHMARKS.md`, `scripts/benchmark_harness.py`).

## Release Discipline

- Every change touching deletion/move logic requires tests.
- Every packaging or CLI contract change requires an installed-command or argument-parser regression test.
- Docs updates are mandatory for behavior changes.
- Changelog entries must state user-visible impact and migration notes.
- Platform-behavior changes require tests that exercise both Windows and POSIX code paths (via real OS or monkeypatched helpers).

## References

- [Docs Index](docs/README.md)
- [Safety](docs/SAFETY.md)
- [Doctor JSON](docs/DOCTOR_JSON.md)
- [Technical Notes](docs/TECHNICAL.md)
- [Changelog](docs/CHANGELOG.md)
