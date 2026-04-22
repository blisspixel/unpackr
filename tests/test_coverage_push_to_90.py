from __future__ import annotations

import json
import types
from datetime import datetime, timedelta
from itertools import chain, repeat
from pathlib import Path

import pytest

import doctor
import vhealth
from core.adaptive_policy import (
    AdaptivePolicy,
    AdaptiveTimeoutCalculator,
    DiskType,
    EnvironmentProfile,
    EnvironmentProfiler,
    OperationOutcome,
    OutcomeType,
)


def _profile(disk_type: DiskType = DiskType.SSD) -> EnvironmentProfile:
    return EnvironmentProfile(
        disk_type=disk_type,
        sequential_read_mbps=500.0,
        random_read_mbps=250.0,
        cpu_score=1.0,
        extraction_speed_mbps=100.0,
        video_decode_fps=120.0,
        last_updated=datetime.now(),
    )


def _checker(tmp_path: Path) -> vhealth.VideoHealthChecker:
    class Cfg:
        video_extensions = [".mp4", ".mkv", ".avi"]

        def get(self, key, default=None):
            if key == "min_sample_size_mb":
                return 1
            return default

    return vhealth.VideoHealthChecker(Cfg())


def _outcome(idx: int, outcome_type: OutcomeType) -> OperationOutcome:
    return OperationOutcome(
        timestamp=datetime.now(),
        operation_type="test",
        file_path=f"/tmp/{idx}.mp4",
        file_size_bytes=10,
        duration_seconds=1.0,
        decision="test",
        outcome=outcome_type,
        metadata={},
    )


def test_environment_profiler_cache_edges_and_detection(tmp_path, monkeypatch):
    cache_file = tmp_path / "env_profile.json"
    stale = _profile()
    stale.last_updated = datetime.now() - timedelta(days=30)
    cache_file.write_text(json.dumps(stale.to_dict()), encoding="utf-8")

    profiler = EnvironmentProfiler(cache_file=cache_file)
    fresh = _profile(DiskType.NVME)
    fresh.last_updated = datetime.now()
    monkeypatch.setattr(profiler, "_profile_system", lambda: fresh)
    monkeypatch.setattr(profiler, "_save_profile", lambda: None)
    assert profiler.get_profile().disk_type == DiskType.NVME

    invalid_cache = tmp_path / "bad.json"
    invalid_cache.write_text("{bad", encoding="utf-8")
    profiler_bad = EnvironmentProfiler(cache_file=invalid_cache)
    monkeypatch.setattr(profiler_bad, "_profile_system", lambda: fresh)
    monkeypatch.setattr(profiler_bad, "_save_profile", lambda: None)
    assert profiler_bad.get_profile().disk_type == DiskType.NVME

    detect = EnvironmentProfiler(cache_file=tmp_path / "detect.json")
    monkeypatch.setattr(detect, "_measure_sequential_read", lambda _p: 3000.0)
    monkeypatch.setattr(detect, "_measure_random_read", lambda _p: 2000.0)
    assert detect._detect_disk_type(tmp_path) == DiskType.NVME

    monkeypatch.setattr(detect, "_measure_sequential_read", lambda _p: 120.0)
    monkeypatch.setattr(detect, "_measure_random_read", lambda _p: 10.0)
    assert detect._detect_disk_type(tmp_path) == DiskType.HDD

    monkeypatch.setattr(detect, "_measure_sequential_read", lambda _p: 120.0)
    monkeypatch.setattr(detect, "_measure_random_read", lambda _p: 60.0)
    assert detect._detect_disk_type(tmp_path) == DiskType.SSD

    monkeypatch.setattr(detect, "_measure_sequential_read", lambda _p: 0.0)
    monkeypatch.setattr(detect, "_measure_random_read", lambda _p: 1.0)
    assert detect._detect_disk_type(tmp_path) == DiskType.UNKNOWN

    monkeypatch.setattr(detect, "_measure_sequential_read", lambda _p: (_ for _ in ()).throw(RuntimeError("boom")))
    assert detect._detect_disk_type(tmp_path) == DiskType.UNKNOWN


def test_environment_profiler_measurement_and_save_edges(tmp_path, monkeypatch):
    profiler = EnvironmentProfiler(cache_file=tmp_path / "env.json")

    seq_times = chain([10.0, 10.0], repeat(10.0))
    monkeypatch.setattr("core.adaptive_policy.time.time", lambda: next(seq_times))
    assert profiler._measure_sequential_read(tmp_path) == 100.0

    rand_times = chain([20.0, 20.0], repeat(20.0))
    monkeypatch.setattr("core.adaptive_policy.time.perf_counter", lambda: next(rand_times))
    assert profiler._measure_random_read(tmp_path) == 50.0

    cpu_times = chain([30.0, 30.0], repeat(30.0))
    monkeypatch.setattr("core.adaptive_policy.time.time", lambda: next(cpu_times))
    assert profiler._measure_cpu_speed() == 1.0

    profiler.profile = _profile()
    monkeypatch.setattr("core.adaptive_policy.json.dump", lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))
    profiler._save_profile()

    profiler.profile = None
    profiler.update_learned_metrics(extraction_speed=200.0, video_decode_fps=180.0)


def test_adaptive_policy_and_timeout_edges(tmp_path, monkeypatch):
    history_file = tmp_path / "policy_history.json"
    policy = AdaptivePolicy("edge", 0.7, 0.5, 0.9, history_file=history_file)
    assert policy.get_statistics()["total_decisions"] == 0

    for idx in range(12):
        policy.record_outcome(_outcome(idx, OutcomeType.TRUE_POSITIVE if idx % 2 == 0 else OutcomeType.TRUE_NEGATIVE))
    assert policy.decide_threshold() == pytest.approx(policy.base_threshold)

    policy_only_fp = AdaptivePolicy("only-fp", 0.7, 0.5, 0.9, history_file=tmp_path / "only-fp.json")
    for idx in range(12):
        policy_only_fp.record_outcome(_outcome(idx, OutcomeType.FALSE_POSITIVE))
    assert policy_only_fp.get_statistics()["false_negative_rate"] == 0.0

    invalid_history = tmp_path / "invalid_history.json"
    invalid_history.write_text("{bad", encoding="utf-8")
    AdaptivePolicy("broken", 0.7, 0.5, 0.9, history_file=invalid_history)

    policy.history_file = tmp_path / "save-fail" / "policy.json"
    monkeypatch.setattr("core.adaptive_policy.json.dump", lambda *a, **k: (_ for _ in ()).throw(OSError("deny")))
    policy._save_history()

    class FakeProfiler:
        def __init__(self, disk_type):
            self._profile = _profile(disk_type)
            self.updated = []

        def get_profile(self, force_refresh: bool = False):
            return self._profile

        def update_learned_metrics(self, extraction_speed=None, video_decode_fps=None):
            self.updated.append((extraction_speed, video_decode_fps))

    hdd = AdaptiveTimeoutCalculator(FakeProfiler(DiskType.HDD))
    ssd = AdaptiveTimeoutCalculator(FakeProfiler(DiskType.SSD))
    nvme = AdaptiveTimeoutCalculator(FakeProfiler(DiskType.NVME))
    unknown = AdaptiveTimeoutCalculator(FakeProfiler(DiskType.UNKNOWN))
    size = 500 * 1024 * 1024
    assert hdd.calculate_extraction_timeout(size) >= ssd.calculate_extraction_timeout(size)
    assert ssd.calculate_extraction_timeout(size) >= nvme.calculate_extraction_timeout(size)
    assert unknown.calculate_extraction_timeout(size) >= nvme.calculate_extraction_timeout(size)

    calc = AdaptiveTimeoutCalculator(FakeProfiler(DiskType.SSD))
    for _ in range(101):
        calc.record_extraction_time(100 * 1024 * 1024, 0.0)
        calc.record_validation_time(120.0, 0.0)
    assert len(calc.extraction_times) == 100
    assert len(calc.validation_times) == 100


def test_doctor_additional_branches(tmp_path, monkeypatch, capsys):
    doc = doctor.UnpackrDoctor()
    config_dir = tmp_path / "config_files"
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"tool_paths": {}, "video_extensions": [".mp4"]}', encoding="utf-8")
    (config_dir / "comments.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(doctor, "__file__", str(tmp_path / "doctor.py"))

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name in {"psutil", "colorama"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(doctor, "__import__", fake_import, raising=False)
    doc.check_dependencies()
    doc.check_config_file()
    doc.check_comments_file()
    doc.check_disk_space()

    exe = tmp_path / "7z.exe"
    exe.write_text("", encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return types.SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    found, path = doc.check_tool("7z", [str(exe)], critical=True)
    assert found is True and path == str(exe)
    assert calls[0] == [str(exe)]

    monkeypatch.setattr("shutil.disk_usage", lambda _p: (100, 95, 4 * (2**30)))
    doc.check_disk_space()
    monkeypatch.setattr("shutil.disk_usage", lambda _p: (100, 92, 7 * (2**30)))
    doc.check_disk_space()

    def import_missing(name, *args, **kwargs):
        if name == "core.video_processor":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(doctor, "__import__", import_missing, raising=False)
    doc.check_core_modules()

    monkeypatch.setattr(Path, "mkdir", lambda self, exist_ok=False: (_ for _ in ()).throw(OSError("deny")))
    doc.check_log_directory()

    doc.print_summary()
    out = capsys.readouterr().out
    assert "Warnings" in out
    assert "Critical Issues" in out


def test_vhealth_duplicate_and_main_branches(tmp_path, monkeypatch):
    checker = _checker(tmp_path)
    checker._active_root = tmp_path.resolve(strict=False)

    fav = tmp_path / "fav_movie.mp4"
    dup = tmp_path / "movie copy.mp4"
    orig = tmp_path / "movie.mp4"
    same_a = tmp_path / "same_a.mp4"
    same_b = tmp_path / "same_b.mp4"
    dup_name = tmp_path / "clip (copy).mp4"
    dup_name_orig = tmp_path / "clip .mp4"

    fav.write_bytes(b"a" * (1024 * 1024))
    dup.write_bytes(b"a" * (1024 * 1024))
    orig.write_bytes(b"a" * (1024 * 1024))
    same_a.write_bytes(b"b" * (1024 * 1024))
    same_b.write_bytes((b"b" * (1024 * 1024)) + (b"c" * 65536))
    dup_name.write_bytes((b"d" * (1024 * 1024)) + (b"e" * 32768))
    dup_name_orig.write_bytes(b"d" * (1024 * 1024))

    monkeypatch.setattr(checker, "_get_duration", lambda p: 60.0 if p in {same_a, same_b} else None)
    checker._detect_duplicates([fav, dup, orig, same_a, same_b, dup_name, dup_name_orig])

    reasons = {reason for _, _, reason in checker.duplicate_videos}
    assert "Exact match (size + hash)" in reasons
    assert "Same duration + hash" in reasons
    assert any("Filename pattern" in reason for reason in reasons)
    assert "Duplicate filename pattern" in reasons

    class DummyChecker:
        def __init__(self, config):
            self.sample_threshold_mb = 1

        def check_path(self, *args, **kwargs):
            raise KeyboardInterrupt()

        def print_summary(self, auto_delete=False):
            return None

    args = types.SimpleNamespace(
        path=str(tmp_path),
        clean=False,
        delete_bad=False,
        min_resolution=None,
        skip_samples=False,
        config=None,
        verbose=False,
    )
    monkeypatch.setattr(vhealth.argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(vhealth, "VideoHealthChecker", DummyChecker)
    monkeypatch.setattr(vhealth, "Config", lambda config_path=None: object())
    with pytest.raises(SystemExit, match="1"):
        vhealth.main()

    class FailingChecker(DummyChecker):
        def check_path(self, *args, **kwargs):
            raise RuntimeError("boom")

    args.clean = True
    monkeypatch.setattr(vhealth.argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(vhealth, "VideoHealthChecker", FailingChecker)
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)
    with pytest.raises(SystemExit, match="1"):
        vhealth.main()
