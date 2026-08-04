#!/usr/bin/env python3
"""
Unpackr micro-benchmark harness.

Produces a JSON report with hardware profile + disk/CPU measurements so
performance work can attach before/after evidence per platform.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running from a source checkout without install.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adaptive_policy import EnvironmentProfiler  # noqa: E402
from utils.filesystem_policy import probe_filesystem  # noqa: E402
from utils.platform_support import platform_label  # noqa: E402

SCHEMA_VERSION = 1

# Metric keys used for before/after deltas (higher is better unless noted).
_COMPARE_METRICS = (
    "sequential_read_mbps",
    "random_read_mbps",
    "cpu_score",
    "default_extraction_speed_mbps",
    "default_video_decode_fps",
)


def _hardware_profile() -> dict[str, Any]:
    return {
        "platform": platform_label(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count": __import__("os").cpu_count(),
    }


def run_benchmark(work_dir: Path | None = None) -> dict[str, Any]:
    """Run micro-benchmarks and return a serializable report."""
    started = time.perf_counter()
    base = work_dir or Path.cwd()
    cache = base / ".unpackr-benchmark-cache.json"
    profiler = EnvironmentProfiler(cache_file=cache)
    # Force a fresh profile rather than reusing a potentially stale cache.
    if cache.exists():
        cache.unlink()
    profile = profiler.get_profile(force_refresh=True)
    fs_probe = probe_filesystem(work_dir)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "hardware": _hardware_profile(),
        "filesystem": fs_probe.to_dict(),
        "metrics": {
            "disk_type": profile.disk_type.name if profile.disk_type else "UNKNOWN",
            "sequential_read_mbps": round(profile.sequential_read_mbps, 3),
            "random_read_mbps": round(profile.random_read_mbps, 3),
            "cpu_score": round(profile.cpu_score, 3),
            "default_extraction_speed_mbps": round(profile.extraction_speed_mbps, 3),
            "default_video_decode_fps": round(profile.video_decode_fps, 3),
        },
        "notes": [
            "These are micro-benchmarks for relative comparison, not guaranteed throughput.",
            "Attach this JSON as before/after evidence when proposing performance changes.",
            "Do not enable concurrency work without regression evidence against this baseline.",
            "Use --compare before.json after.json to emit a delta report.",
        ],
    }
    return report


def load_report(path: Path) -> dict[str, Any]:
    """Load a previously written benchmark JSON report."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Benchmark report must be a JSON object: {path}")
    return payload


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """
    Compare two harness reports.

    Returns a structured delta suitable for PR evidence. Does not invent
    pass/fail thresholds for micro-benchmark noise; callers interpret deltas.
    """
    before_metrics = before.get("metrics") if isinstance(before.get("metrics"), dict) else {}
    after_metrics = after.get("metrics") if isinstance(after.get("metrics"), dict) else {}

    deltas: dict[str, Any] = {}
    for key in _COMPARE_METRICS:
        b_raw = before_metrics.get(key)
        a_raw = after_metrics.get(key)
        try:
            b_val = float(b_raw)  # type: ignore[arg-type]
            a_val = float(a_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            deltas[key] = {
                "before": b_raw,
                "after": a_raw,
                "delta": None,
                "pct_change": None,
                "status": "missing",
            }
            continue
        delta = a_val - b_val
        pct = None if b_val == 0 else round((delta / b_val) * 100.0, 3)
        deltas[key] = {
            "before": b_val,
            "after": a_val,
            "delta": round(delta, 3),
            "pct_change": pct,
            "status": "ok",
        }

    before_hw = before.get("hardware") if isinstance(before.get("hardware"), dict) else {}
    after_hw = after.get("hardware") if isinstance(after.get("hardware"), dict) else {}
    host_match = (
        before_hw.get("system") == after_hw.get("system")
        and before_hw.get("machine") == after_hw.get("machine")
        and before_hw.get("python") == after_hw.get("python")
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "comparison": "after_minus_before",
        "host_match": host_match,
        "before": {
            "generated_at": before.get("generated_at"),
            "hardware": before_hw,
            "disk_type": before_metrics.get("disk_type"),
        },
        "after": {
            "generated_at": after.get("generated_at"),
            "hardware": after_hw,
            "disk_type": after_metrics.get("disk_type"),
        },
        "deltas": deltas,
        "notes": [
            "Positive delta means higher after-value (usually better for throughput metrics).",
            "Compare only within the same host class and path class (local SSD vs NAS).",
            "Micro-benchmark noise can dominate small changes; prefer multi-run medians for claims.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Unpackr micro-benchmarks and emit JSON.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Write JSON report to this path (default: stdout)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Directory used for temporary probe files (default: cwd temp)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        type=Path,
        help="Compare two existing reports instead of running a new benchmark",
    )
    args = parser.parse_args(argv)

    if args.compare:
        before = load_report(args.compare[0])
        after = load_report(args.compare[1])
        report: dict[str, Any] = compare_reports(before, after)
    else:
        report = run_benchmark(args.work_dir)

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote benchmark report to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
