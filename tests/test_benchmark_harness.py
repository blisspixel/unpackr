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
    assert report["schema_version"] == harness.SCHEMA_VERSION
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
            "schema_version": 1,
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


def test_compare_reports_emits_deltas():
    before = {
        "generated_at": "t0",
        "hardware": {"system": "Windows", "machine": "AMD64", "python": "3.14.5"},
        "metrics": {
            "disk_type": "SSD",
            "sequential_read_mbps": 100.0,
            "random_read_mbps": 50.0,
            "cpu_score": 5.0,
            "default_extraction_speed_mbps": 40.0,
            "default_video_decode_fps": 80.0,
        },
    }
    after = {
        "generated_at": "t1",
        "hardware": {"system": "Windows", "machine": "AMD64", "python": "3.14.5"},
        "metrics": {
            "disk_type": "SSD",
            "sequential_read_mbps": 120.0,
            "random_read_mbps": 45.0,
            "cpu_score": 5.0,
            "default_extraction_speed_mbps": 40.0,
            "default_video_decode_fps": 80.0,
        },
    }
    delta = harness.compare_reports(before, after)
    assert delta["host_match"] is True
    assert delta["deltas"]["sequential_read_mbps"]["delta"] == 20.0
    assert delta["deltas"]["random_read_mbps"]["pct_change"] == -10.0


def test_compare_cli_writes_delta(tmp_path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    out = tmp_path / "delta.json"
    sample = {
        "generated_at": "t0",
        "hardware": {"system": "Linux", "machine": "x86_64", "python": "3.12.0"},
        "metrics": {
            "sequential_read_mbps": 10.0,
            "random_read_mbps": 5.0,
            "cpu_score": 1.0,
            "default_extraction_speed_mbps": 1.0,
            "default_video_decode_fps": 1.0,
        },
    }
    before_path.write_text(json.dumps(sample), encoding="utf-8")
    sample["metrics"]["sequential_read_mbps"] = 20.0
    after_path.write_text(json.dumps(sample), encoding="utf-8")

    assert harness.main(["--compare", str(before_path), str(after_path), "-o", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["deltas"]["sequential_read_mbps"]["delta"] == 10.0


def test_published_baseline_shape():
    published = ROOT / "benchmarks" / "published" / "local-windows-dev.json"
    assert published.is_file()
    payload = json.loads(published.read_text(encoding="utf-8"))
    assert "hardware" in payload
    assert "metrics" in payload
    assert payload["hardware"]["system"]
    assert "sequential_read_mbps" in payload["metrics"]
