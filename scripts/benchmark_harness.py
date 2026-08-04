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

# Allow running from a source checkout without install.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adaptive_policy import EnvironmentProfiler  # noqa: E402
from utils.filesystem_policy import probe_filesystem  # noqa: E402
from utils.platform_support import platform_label  # noqa: E402


def _hardware_profile() -> dict:
    return {
        "platform": platform_label(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count": __import__("os").cpu_count(),
    }


def run_benchmark(work_dir: Path | None = None) -> dict:
    """Run micro-benchmarks and return a serializable report."""
    started = time.perf_counter()
    cache = (work_dir or Path.cwd()) / ".unpackr-benchmark-cache.json"
    profiler = EnvironmentProfiler(cache_file=cache)
    # Force a fresh profile rather than reusing a potentially stale cache.
    if cache.exists():
        cache.unlink()
    profile = profiler.get_profile(force_refresh=True)
    fs_probe = probe_filesystem(work_dir)

    report = {
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
        ],
    }
    return report


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
    args = parser.parse_args(argv)

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
