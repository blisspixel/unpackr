# Benchmarks

Unpackr treats performance work as evidence-driven. No concurrency or “make it faster” change is accepted without before/after numbers and unchanged safety regressions.

## Harness

```bash
python scripts/benchmark_harness.py
python scripts/benchmark_harness.py -o benchmarks/baseline.json
python scripts/benchmark_harness.py --compare benchmarks/before.json benchmarks/after.json
python scripts/benchmark_harness.py --compare before.json after.json -o benchmarks/delta.json
```

Output fields (schema version 1):

| Field | Meaning |
|-------|---------|
| `schema_version` | Report schema integer |
| `hardware` | OS, machine, Python, CPU count |
| `filesystem` | case sensitivity, symlink support, non-ASCII names |
| `metrics.sequential_read_mbps` | rough sequential read probe |
| `metrics.random_read_mbps` | rough random read probe |
| `metrics.cpu_score` | relative CPU micro-score |
| `metrics.default_extraction_speed_mbps` | starting estimate used by adaptive policy |

These are **micro-benchmarks** for relative comparison on one machine, not guaranteed archive throughput.

### Compare mode

`--compare BEFORE AFTER` loads two reports and emits:

- `host_match` — whether system/machine/python match (warn when false)
- `deltas.<metric>.{before,after,delta,pct_change}` — after minus before

Use the same machine and path class (local SSD vs NAS) for claims. Small single-run deltas are noise; prefer multi-run medians for product claims.

## Published sample baselines

Checked-in samples under `benchmarks/published/` document hardware-profile shape for operators and CI readers. They are **not** SLAs.

| File | Host class | Notes |
|------|------------|-------|
| `benchmarks/published/local-windows-dev.json` | Windows 11, AMD64, Python 3.14, local SSD class | Developer workstation sample |

Regenerate:

```bash
python scripts/benchmark_harness.py -o benchmarks/published/local-windows-dev.json
```

CI (Linux, Python 3.11) runs a harness **smoke** that only checks schema shape and non-negative metrics. Smoke numbers are not SLAs and must not be compared to operator NAS results.

## Required Evidence For Performance PRs

1. Baseline JSON from the harness on the target OS.
2. After-change JSON from the same machine/path class (local SSD vs NAS called out).
3. Optional delta via `python scripts/benchmark_harness.py --compare before.json after.json`.
4. Full regression suite still green (including safety/filesystem quirk tests).
5. Safety stress matrix green: `tests/test_safety_stress_matrix.py` (delete races, validated-video invariant, resume-state concurrent marks).
6. Notes on whether the workload was CPU-bound, disk-bound, or tool-bound (`7z`/`ffmpeg`).

## Safety regression matrix (concurrency gate)

Before enabling parallel extraction, validation, or deletes, all of the following must pass:

| Risk | Coverage |
|------|----------|
| Content appears between removable check and delete | `TestDeleteRaceMatrix` |
| Symlink/junction delete refusal | `TestDeleteRaceMatrix.test_safe_delete_refuses_symlink_root` |
| Validated video never deleted | `TestInvariantStressMatrix` |
| Resume state survives multi-writer access without crash | `TestRunStateConcurrencyMatrix` |
| Threaded probe + late file injection | `TestHandlerStressMatrix` |

Current product code remains **sequential by design**. The matrix documents fail-closed behavior under race-like conditions; it does not authorize concurrency.

## Interpreting Results

- Large sequential/random gaps usually mean HDD or contended NAS.
- Very high sequential rates on CI often reflect tmpfs and should not be compared to operator NAS numbers.
- CPU score is relative; compare only within the same host class.

## What Is Intentionally Deferred

Parallel extraction/validation remains deferred until:

1. This harness is the default evidence path in CI/docs (done).
2. A safety regression matrix for concurrent deletes/moves exists (done: `tests/test_safety_stress_matrix.py`).
3. At least one real multi-archive operator workload is measured with and without concurrency (still required for any concurrency PR).

Until then, reliability beats speculative parallelism.
