"""Regression checks for the micro-benchmark harness."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "scripts" / "benchmark_harness.py"
SPEC = importlib.util.spec_from_file_location("unpackr_benchmark_harness", HARNESS_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = harness
SPEC.loader.exec_module(harness)


def test_run_benchmark_emits_required_sections(tmp_path):
    report = harness.run_benchmark(tmp_path)
    assert "hardware" in report
    assert "filesystem" in report
    assert "metrics" in report
    assert report["hardware"]["platform"]
    assert report["metrics"]["sequential_read_mbps"] >= 0
    assert report["metrics"]["cpu_score"] > 0


def test_benchmark_cli_writes_json(tmp_path, monkeypatch):
    out = tmp_path / "bench.json"
    monkeypatch.setattr(
        harness,
        "run_benchmark",
        lambda work_dir=None: {
            "generated_at": "now",
            "duration_seconds": 0.1,
            "hardware": {"platform": "test"},
            "filesystem": {"case_sensitive": True},
            "metrics": {"sequential_read_mbps": 1.0, "cpu_score": 1.0},
            "notes": [],
        },
    )
    assert harness.main(["--output", str(out), "--work-dir", str(tmp_path)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["hardware"]["platform"] == "test"
