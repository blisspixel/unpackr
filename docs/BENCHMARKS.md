# Benchmarks

Unpackr treats performance work as evidence-driven. No concurrency or “make it faster” change is accepted without before/after numbers and unchanged safety regressions.

## Harness

```bash
python scripts/benchmark_harness.py
python scripts/benchmark_harness.py -o benchmarks/baseline.json
```

Output fields:

| Field | Meaning |
|-------|---------|
| `hardware` | OS, machine, Python, CPU count |
| `filesystem` | case sensitivity, symlink support, non-ASCII names |
| `metrics.sequential_read_mbps` | rough sequential read probe |
| `metrics.random_read_mbps` | rough random read probe |
| `metrics.cpu_score` | relative CPU micro-score |
| `metrics.default_extraction_speed_mbps` | starting estimate used by adaptive policy |

These are **micro-benchmarks** for relative comparison on one machine, not guaranteed archive throughput.

## Required Evidence For Performance PRs

1. Baseline JSON from the harness on the target OS.
2. After-change JSON from the same machine/path class (local SSD vs NAS called out).
3. Full regression suite still green (including safety/filesystem quirk tests).
4. Notes on whether the workload was CPU-bound, disk-bound, or tool-bound (`7z`/`ffmpeg`).

## Interpreting Results

- Large sequential/random gaps usually mean HDD or contended NAS.
- Very high sequential rates on CI often reflect tmpfs and should not be compared to operator NAS numbers.
- CPU score is relative; compare only within the same host class.

## What Is Intentionally Deferred

Parallel extraction/validation is deferred until:

1. This harness is the default evidence path in CI/docs (done).
2. A safety regression matrix for concurrent deletes/moves exists.
3. At least one real multi-archive operator workload is measured with and without concurrency.

Until then, reliability beats speculative parallelism.
