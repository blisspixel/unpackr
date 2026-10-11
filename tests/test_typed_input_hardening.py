"""Regression tests for malformed-input paths found while tightening type checking."""

import json
import os
import sys
from datetime import datetime

import pytest

from core.adaptive_policy import DiskType, EnvironmentProfile, EnvironmentProfiler
from core.remover import RunJournal
from core.structured_events import EventAnalyzer, EventEmitter, EventType
from utils import service
from utils.defensive import InputValidator, ValidationError
from utils.system_check import SystemCheck


def test_run_journal_skips_json_lines_that_are_not_objects(tmp_path):
    journal = tmp_path / "run.jsonl"
    journal.write_text('[1, 2]\n"text"\n{"op": "move"}\nnot json\n', encoding="utf-8")
    assert RunJournal.read(journal) == [{"op": "move"}]


def test_service_manifests_skip_non_object_json(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "manifest_dir", lambda: tmp_path)
    (tmp_path / "a.json").write_text("[]", encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"name": "unpackr-x"}), encoding="utf-8")
    manifests = service._manifests()
    assert [m["name"] for m in manifests] == ["unpackr-x"]


def test_event_analyzer_keeps_loading_after_malformed_records(tmp_path):
    log_file = tmp_path / "events.jsonl"
    emitter = EventEmitter(log_file=log_file, enable_console=False)
    good = emitter.emit(EventType.VIDEO_DISCOVERED, "first")
    with open(log_file, "a", encoding="utf-8") as handle:
        handle.write("[1, 2, 3]\n")
        handle.write(json.dumps({**good.to_dict(), "unexpected": True}) + "\n")
    emitter.emit(EventType.VIDEO_DISCOVERED, "after the bad lines")

    analyzer = EventAnalyzer(log_file)
    analyzer.load_events()
    assert [e.message for e in analyzer.events] == ["first", "after the bad lines"]


@pytest.mark.parametrize("payload", ["[]", '{"disk_type": "SSD"}', '{"unknown": 1}'])
def test_environment_profiler_reprofiles_on_corrupt_cache(tmp_path, monkeypatch, payload):
    cache = tmp_path / "env_profile.json"
    cache.write_text(payload, encoding="utf-8")
    profiler = EnvironmentProfiler(cache_file=cache)
    fresh = EnvironmentProfile(
        disk_type=DiskType.SSD,
        sequential_read_mbps=1.0,
        random_read_mbps=1.0,
        cpu_score=1.0,
        extraction_speed_mbps=1.0,
        video_decode_fps=1.0,
        last_updated=datetime.now(),
    )
    monkeypatch.setattr(profiler, "_profile_system", lambda: fresh)
    assert profiler.get_profile() is fresh


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX execute permission")
def test_check_tool_skips_entries_that_cannot_be_executed(tmp_path):
    not_executable = tmp_path / "7z"
    not_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(not_executable, 0o644)
    checker = SystemCheck(config={"tool_paths": {"7z": [str(not_executable)]}})
    # Before: PermissionError escaped check_tool; now the entry is skipped.
    checker.check_tool("7z")


def test_validate_path_rejects_escape_from_base_dir(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(ValidationError, match="escapes base directory"):
        InputValidator.validate_path(tmp_path / "elsewhere", base_dir=base)
    assert InputValidator.validate_path(base / "inside", base_dir=base) == (base / "inside").resolve()
