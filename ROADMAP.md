# Roadmap

This roadmap is reliability-first: safety, correctness, cross-platform parity, observability, then performance.

## Version Focus

- Current line: `1.4.x` (latest: `1.4.0`, August 2026) — first-class **Windows, Linux, and macOS**
- Primary objective: keep destructive operations auditable and deterministic on every supported OS

## Quality Baseline

- CI quality gate is `80%` coverage minimum.
- The full regression suite must pass before merge.
- Dependency/version policy is enforced by `unpackr-doctor` and runtime preflight.
- Installed CLI entry points and documented path flags are covered by regression and CI smoke tests.
- Python support floor is `3.11+` (CI matrix includes `3.11` through `3.14`).
- Active documentation stays under `docs/`; superseded content belongs in `docs/archive/`.
- Platform policy lives in `utils/platform_support.py` rather than ad-hoc `sys.platform` checks.

## Guiding Principles

- Fail closed on uncertainty.
- Keep defaults conservative.
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

### Now: Cross-Platform Foundations (`1.4.0`)

Goal: make Linux and macOS supported platforms with the same safety contract as Windows.

Acceptance criteria:
- Runtime no longer assumes Windows for tool discovery, process conflict checks, or force-delete fallbacks.
- `unpackr-doctor` reports platform-correct tool guidance and helper-process conflicts on Linux/macOS.
- Bundled/default `tool_paths` prefer PATH command names; Windows absolute paths remain optional fallbacks.
- CI runs a meaningful non-Windows regression suite (not help-text smoke only).
- README/BUILD/CONFIGURATION document multi-OS install and tool packaging (`p7zip`, `par2cmdline`, `ffmpeg`).
- Filename sanitization stays conservative for shared/network volumes (Windows-hostile characters remain scrubbed).

Status:
- Complete enough for `1.4.0` foundations. Follow-on parity work continues below.

### Now: Cross-Platform Parity Hardening (`1.4.x`)

Goal: make Linux/macOS behavior as boringly reliable as Windows for real operator workloads.

Acceptance criteria:
- Full regression suite green on Linux CI for every supported Python version.
- Expanded macOS suite for path, delete, doctor, and archive safety modules.
- Integration coverage with real `7z`/`ffmpeg` where the runner provides them.
- Documented package-manager recipes:
  - Debian/Ubuntu: `p7zip-full`, `par2`, `ffmpeg`
  - Fedora/RHEL: `p7zip`, `par2cmdline`, `ffmpeg`
  - macOS Homebrew: `p7zip`, `par2`, `ffmpeg`
- Optional shell wrappers (`unpackr.sh`) for environments that prefer non-batch launchers.
- Explicit matrix of filesystem quirks: case-sensitive volumes, APFS/ZFS, bind mounts, SMB/NFS.

Status:
- In progress. Full Linux CI suite, expanded macOS suite, optional real-tool tests, POSIX launchers, doctor package-manager hints, and `docs/PLATFORMS.md` are landing now. Filesystem quirk matrix remains for Phase C.

### Next: Observability And Automation

Goal: make runtime behavior machine-verifiable in CI and local scripts.

Acceptance criteria:
- CI can block on doctor output and explicit issue counts.
- Exit semantics are documented and covered by tests.
- Structured outputs include timestamps, status, and actionable remediation hints.

Status:
- In progress. `unpackr-doctor --json` is documented and CI-tested; next target is structured `unpackr` run summaries and richer machine-readable run output.

### Next: Correctness And Recovery Hardening

Goal: reduce false positives/false negatives in processing decisions.

Acceptance criteria:
- Interrupted runs are resumable without duplicate moves or unsafe deletes.
- Archive/video decision paths are reproducibly testable.
- Preservation heuristics have documented limits and examples.

Status:
- In progress. Integration scenarios and destructive-path regression coverage continue to expand, with `core/file_handler.py` and `unpackr.py` receiving the current focus.

### Later: Performance With Evidence

Goal: improve throughput without regressing safety.

Acceptance criteria:
- Benchmark results published with hardware profile details.
- Performance changes must include before/after evidence.
- No safety invariant regressions in stress tests.

Status:
- Pending. Defer concurrency work until benchmark harness and safety regression matrix are in place.

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
