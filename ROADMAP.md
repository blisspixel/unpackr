# Roadmap

This roadmap is reliability-first. Priority order is safety, correctness, observability, then performance.

## Current Focus

Version line: 1.3.x

Primary objective: make destructive operations auditable, deterministic, and hard to misuse.

Current baseline (latest):
- CI quality gate is `80%` coverage minimum.
- Dependency/version policy is enforced by `unpackr-doctor` and runtime preflight.
- Python support floor is `3.11+`.
- Documentation split is enforced: active docs in `docs/`, superseded docs in `docs/archive/`.

## Guiding Principles

- Fail closed on uncertainty.
- Keep defaults conservative.
- Ship measurable reliability gains each iteration.
- Prefer explicit policy over implicit behavior.

## Non-Goals (Current Horizon)

- GUI application
- Cloud sync/integration
- Plugin ecosystem
- Metadata enrichment
- Audio library management

Parallelism is not a blanket non-goal. It is deferred until benchmark-backed designs prove safety and real-world wins on HDD/SSD/NAS profiles.

## Milestones

### M1: Safety Contract Closure

Goal: eliminate ambiguous deletion behavior.

Work:
- Publish strict deletion invariants in `docs/SAFETY.md`.
- Add policy tests for edge cases (permissions, unreadable paths, mixed-content folders).
- Add "why deleted" reason codes to logs for every destructive action.

Acceptance criteria:
- No destructive action occurs without a logged reason.
- Regression suite includes path-access and containment failure cases.
- Dry-run and live-run decisions are policy-equivalent (execution differs, decisions do not).

Status:
- Mostly complete. Continue hardening edge-case deletion reasoning and audit outputs.

### M2: Observability And Automation

Goal: make runtime behavior machine-verifiable in CI and local scripts.

Work:
- Stabilize `unpackr-doctor --json` schema and document compatibility policy.
- Add structured run summary output for `unpackr` (optional JSON mode).
- Standardize exit code semantics across commands.

Acceptance criteria:
- CI can block on doctor output and explicit issue counts.
- Exit semantics are documented and covered by tests.
- Structured outputs include timestamps, status, and actionable remediation hints.

Status:
- In progress. `doctor --json` is documented; next step is structured run-summary output for `unpackr`.

### M3: Correctness And Recovery Hardening

Goal: reduce false positives/false negatives in processing decisions.

Work:
- Expand integration tests for partial archives, broken PAR2 sets, and interrupted runs.
- Add deterministic recovery behavior for cancellations and mid-run failures.
- Validate preservation heuristics against representative mixed media datasets.

Acceptance criteria:
- Interrupted runs are resumable without duplicate moves or unsafe deletes.
- Archive/video decision paths are reproducibly testable.
- Preservation heuristics have documented limits and examples.

Status:
- In progress. Substantial branch coverage exists; continue integration scenarios for interrupted and partial runs.

### M4: Performance With Evidence

Goal: improve throughput without regressing safety.

Work:
- Build benchmark harness for HDD, SSD, and network shares.
- Profile extraction, validation, and folder traversal hotspots.
- Evaluate bounded concurrency only where contention risk is controlled.

Acceptance criteria:
- Benchmark results published with hardware profile details.
- Performance changes must include before/after evidence.
- No safety invariant regressions in stress tests.

Status:
- Pending. Defer concurrency work until benchmark harness and safety regression matrix are in place.

## Risks And Controls

- Risk: accidental data loss.
  Control: stronger invariants, reason-coded logging, dry-run parity tests.
- Risk: dependency drift (Python/tools).
  Control: explicit support matrix, doctor checks, version policy docs.
- Risk: behavioral drift from quick fixes.
  Control: regression-first workflow and stricter release gates.

## Release Discipline

- Every change touching deletion/move logic requires tests.
- Docs updates are mandatory for behavior changes.
- Changelog entries must state user-visible impact and migration notes.

## References

- [README](README.md)
- [Safety](docs/SAFETY.md)
- [Doctor JSON](docs/DOCTOR_JSON.md)
- [Technical Notes](docs/TECHNICAL.md)
- [Changelog](docs/CHANGELOG.md)
