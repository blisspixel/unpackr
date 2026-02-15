# Roadmap

This roadmap is reliability-first: safety, correctness, observability, then performance.

## Version Focus

- Current line: `1.3.x`
- Primary objective: make destructive operations auditable, deterministic, and hard to misuse.

## Quality Baseline

- CI quality gate is `80%` coverage minimum.
- Dependency/version policy is enforced by `unpackr-doctor` and runtime preflight.
- Python support floor is `3.11+`.
- Active documentation stays under `docs/`; superseded content belongs in `docs/archive/`.

## Guiding Principles

- Fail closed on uncertainty.
- Keep defaults conservative.
- Ship measurable reliability gains each iteration.
- Prefer explicit policy over implicit behavior.

## Milestones

### Now: Safety Contract Closure

Goal: eliminate ambiguous deletion behavior.

Acceptance criteria:
- No destructive action occurs without a logged reason.
- Regression suite includes path-access and containment failure cases.
- Dry-run and live-run decisions are policy-equivalent (execution differs, decisions do not).

Status:
- Mostly complete. Continue hardening edge cases and deletion audit trails.

### Next: Observability And Automation

Goal: make runtime behavior machine-verifiable in CI and local scripts.

Acceptance criteria:
- CI can block on doctor output and explicit issue counts.
- Exit semantics are documented and covered by tests.
- Structured outputs include timestamps, status, and actionable remediation hints.

Status:
- In progress. `doctor --json` is documented; next target is structured `unpackr` run summaries.

### Next: Correctness And Recovery Hardening

Goal: reduce false positives/false negatives in processing decisions.

Acceptance criteria:
- Interrupted runs are resumable without duplicate moves or unsafe deletes.
- Archive/video decision paths are reproducibly testable.
- Preservation heuristics have documented limits and examples.

Status:
- In progress. Continue integration scenarios for interrupted and partial runs.

### Later: Performance With Evidence

Goal: improve throughput without regressing safety.

Acceptance criteria:
- Benchmark results published with hardware profile details.
- Performance changes must include before/after evidence.
- No safety invariant regressions in stress tests.

Status:
- Pending. Defer concurrency work until benchmark harness and safety regression matrix are in place.

## Release Discipline

- Every change touching deletion/move logic requires tests.
- Docs updates are mandatory for behavior changes.
- Changelog entries must state user-visible impact and migration notes.

## References

- [Docs Index](docs/README.md)
- [Safety](docs/SAFETY.md)
- [Doctor JSON](docs/DOCTOR_JSON.md)
- [Technical Notes](docs/TECHNICAL.md)
- [Changelog](docs/CHANGELOG.md)
