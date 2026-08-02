from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import doctor
from core.structured_events import EventAnalyzer, EventBuilder, EventEmitter, EventSeverity, EventType, StructuredEvent
from utils.defensive import ErrorRecovery, InputValidator, StateValidator, ValidationError, defensive_wrapper
from utils.system_check import SystemCheck


def test_structured_event_emitter_console_and_file_error_paths(tmp_path):
    emitter = EventEmitter(log_file=tmp_path / "events.jsonl", enable_console=True, enable_file=False)

    with patch("core.structured_events.logger.log") as mock_log:
        event = emitter.emit(
            EventType.VIDEO_DISCOVERED,
            "discovered",
            severity=EventSeverity.WARNING,
            context={"path": "/tmp/video.mp4", "size": 123, "ignored": "x"},
        )
    assert event in emitter.event_buffer
    assert "path=/tmp/video.mp4" in mock_log.call_args.args[1]
    assert "size=123" in mock_log.call_args.args[1]

    emitter = EventEmitter(log_file=tmp_path / "events.jsonl", enable_console=False, enable_file=True)
    with (
        patch("builtins.open", side_effect=OSError("boom")),
        patch("core.structured_events.logger.error") as mock_error,
    ):
        emitter.emit(EventType.VIDEO_DISCOVERED, "broken")
    assert "Failed to write event to file" in mock_error.call_args.args[0]


def test_structured_events_query_until_and_builder_variants(tmp_path):
    emitter = EventEmitter(log_file=tmp_path / "events.jsonl", enable_console=False)
    builder = EventBuilder(emitter)
    old = emitter.emit(EventType.VIDEO_DISCOVERED, "old")
    new = emitter.emit(EventType.VIDEO_DISCOVERED, "new")
    old.timestamp = new.timestamp.replace(year=new.timestamp.year - 1)

    filtered = emitter.query_events(until=new.timestamp.replace(year=new.timestamp.year - 1))
    assert filtered == [old]

    archive = tmp_path / "missing.rar"
    completed = builder.archive_extraction_completed(archive, duration=0, files_extracted=1)
    assert completed.metadata["extraction_speed_mbps"] == 0

    failed = builder.archive_extraction_failed(Path("/tmp/a.rar"), "crc")
    assert failed.event_type == EventType.ARCHIVE_EXTRACTION_FAILED

    discovered = builder.video_discovered(Path("/tmp/video.mkv"), 1024)
    assert discovered.context["size_mb"] > 0

    adjusted = builder.policy_threshold_adjusted("policy", 0.1, 0.2, "reason")
    assert adjusted.context["reason"] == "reason"

    profiled = builder.environment_profiled("ssd", 100.0, 50.0)
    assert profiled.context["disk_type"] == "ssd"


def test_event_analyzer_edge_paths(tmp_path):
    missing = EventAnalyzer(tmp_path / "missing.jsonl")
    missing.load_events()
    assert missing.events == []
    assert missing.get_success_rate("VIDEO") == 0.0
    assert missing.get_average_duration(EventType.VIDEO_DISCOVERED) is None
    assert missing.get_error_summary() == {}
    assert missing.detect_performance_degradation(EventType.VIDEO_DISCOVERED) is False

    log_file = tmp_path / "events.jsonl"
    valid_event = StructuredEvent(
        event_id="1",
        event_type=EventType.VIDEO_VALIDATION_FAILED,
        timestamp=StructuredEvent.from_dict(
            {
                "event_id": "x",
                "event_type": "VIDEO_DISCOVERED",
                "timestamp": "2026-01-01T00:00:00",
                "severity": "INFO",
                "message": "m",
                "context": {},
                "metadata": {},
                "session_id": None,
                "parent_event_id": None,
            }
        ).timestamp,
        severity=EventSeverity.ERROR,
        message="bad",
        context={},
    )
    log_file.write_text("{bad json}\n" + valid_event.to_json() + "\n", encoding="utf-8")
    analyzer = EventAnalyzer(log_file)
    analyzer.load_events()
    assert len(analyzer.events) == 1
    assert analyzer.get_error_summary() == {"VIDEO_VALIDATION_FAILED": 1}

    with (
        patch("builtins.open", side_effect=OSError("boom")),
        patch("core.structured_events.logger.error") as mock_error,
    ):
        analyzer.load_events()
    assert "Failed to load events" in mock_error.call_args.args[0]


def test_system_check_resolution_and_version_paths(monkeypatch, tmp_path):
    checker = SystemCheck(config={"tool_paths": {"7z": "7z-custom"}})
    monkeypatch.setattr("utils.system_check.shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd else None)
    monkeypatch.setattr("utils.system_check.os.path.isfile", lambda path: path.endswith(".exe"))

    assert checker.check_tool("unknown") is False
    assert checker._resolve_tool_path("") == ""
    assert checker._resolve_tool_path("./bin/tool.exe") == ""
    assert checker._resolve_tool_path("7z") == "/usr/bin/7z"
    assert checker._extract_version_tuple("no version here") is None
    assert checker._format_version((1, 2, 3)) == "1.2.3"
    assert checker._is_version_at_least((1, 2), (1, 2, 0)) is True

    checker.get_tool_command = lambda _tool: []
    assert checker._get_tool_version("7z") is None


def test_system_check_evaluate_display_and_commands(monkeypatch, capsys):
    checker = SystemCheck(config={"tool_paths": {"7z": "7z-custom", "ffmpeg": None}})
    monkeypatch.setattr(checker, "_get_tool_version", lambda tool: {"7z": (21, 0), "ffmpeg": None}.get(tool))
    assert checker._evaluate_tool_version("missing") == (True, "version policy not configured")
    assert checker._evaluate_tool_version("ffmpeg") == (True, "version unknown")
    assert checker._evaluate_tool_version("7z")[0] is False

    checker._version_status = {"7z": (False, "21.0 (need 22.0+)"), "par2": (True, "0.8.1")}
    can_proceed = checker.display_tool_status({"7z": True, "par2": False, "ffmpeg": True})
    out = capsys.readouterr().out
    assert can_proceed is False
    assert "OLD" in out and "SKIP" in out

    checker._working_paths = {"7z": "C:/7z.exe"}
    assert checker.get_tool_command("7z") == ["C:/7z.exe"]
    assert checker.get_tool_command("unknown") == []

    checker = SystemCheck(config={"tool_paths": {"7z": "7z-custom"}})
    monkeypatch.setattr(checker, "_resolve_tool_path", lambda path: {"7z-custom": "/bin/7z-custom"}.get(path, ""))
    assert checker.get_tool_command("7z") == ["/bin/7z-custom"]
    assert checker.get_tool_command("ffmpeg") == []


def test_system_check_process_kill_and_warn_paths(monkeypatch, capsys):
    checker = SystemCheck()
    monkeypatch.setattr("utils.system_check.sys.platform", "win32")
    calls = []
    monkeypatch.setattr(
        "utils.system_check.subprocess.run",
        lambda cmd, **kwargs: calls.append(cmd) or types.SimpleNamespace(stdout="", stderr=""),
    )
    assert checker.kill_processes(["7-Zip", "par2"]) is True
    assert any("taskkill" in cmd[0] for cmd in calls)

    monkeypatch.setattr("utils.system_check.sys.platform", "linux")
    calls.clear()
    assert checker.kill_processes(["7-Zip", "par2"]) is True
    assert any("pkill" in cmd[0] for cmd in calls)

    monkeypatch.setattr("utils.system_check.subprocess.run", Mock(side_effect=RuntimeError("boom")))
    assert checker.kill_processes(["7-Zip"]) is False

    checker = SystemCheck()
    monkeypatch.setattr(checker, "check_running_processes", lambda: (False, []))
    assert checker.warn_running_processes() is True

    checker = SystemCheck()
    monkeypatch.setattr(checker, "check_running_processes", lambda: (True, ["7-Zip"]))
    monkeypatch.setattr(checker, "kill_processes", lambda _names: (_ for _ in ()).throw(KeyboardInterrupt()))
    with patch("time.sleep", lambda *_: None):
        assert checker.warn_running_processes() is False
    assert "Aborted by user" in capsys.readouterr().out


def test_defensive_input_validator_and_state_edges(tmp_path, monkeypatch):
    with pytest.raises(ValidationError):
        InputValidator.validate_path(tmp_path / "missing", must_be_dir=True, must_exist=True)

    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError):
        InputValidator.validate_path(file_path, must_be_dir=True)
    with pytest.raises(ValidationError):
        InputValidator.validate_path(tmp_path, must_be_file=True)

    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError):
        InputValidator.validate_path(outside, must_exist=True, base_dir=base)

    with pytest.raises(ValidationError):
        InputValidator.validate_string(None)
    assert InputValidator.validate_string(None, allow_none=True) is None
    with pytest.raises(ValidationError):
        InputValidator.validate_string(1)
    with pytest.raises(ValidationError):
        InputValidator.validate_string("x", min_length=2)
    with pytest.raises(ValidationError):
        InputValidator.validate_string("xxx", max_length=2)

    assert InputValidator.validate_int(None, allow_none=True) is None
    with pytest.raises(ValidationError):
        InputValidator.validate_int(None)
    with pytest.raises(ValidationError):
        InputValidator.validate_int("abc")

    assert InputValidator.validate_list(None, allow_none=True) is None
    with pytest.raises(ValidationError):
        InputValidator.validate_list(None)
    with pytest.raises(ValidationError):
        InputValidator.validate_list("bad")
    with pytest.raises(ValidationError):
        InputValidator.validate_list([], allow_empty=False)

    missing = tmp_path / "missing.txt"
    assert StateValidator.check_file_accessible(missing) is False
    assert StateValidator.check_dir_writable(missing) is False
    assert StateValidator.validate_config_dict([], ["a"]) is False
    assert StateValidator.validate_config_dict({"a": 1}, ["a", "b"]) is False

    monkeypatch.setattr("shutil.disk_usage", Mock(side_effect=RuntimeError("boom")))
    assert StateValidator.check_disk_space(tmp_path, required_mb=100) is False


def test_defensive_error_recovery_and_wrapper_edges(tmp_path, monkeypatch):
    folder = tmp_path / "folder"
    folder.mkdir()
    child = folder / "x.txt"
    child.write_text("x", encoding="utf-8")
    assert ErrorRecovery.safe_delete(folder) is True

    path = tmp_path / "stubborn.txt"
    path.write_text("x", encoding="utf-8")
    with patch.object(Path, "unlink", side_effect=RuntimeError("boom")), patch("time.sleep", lambda *_: None):
        assert ErrorRecovery.safe_delete(path, max_attempts=2) is False

    src = tmp_path / "source.txt"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "dest.txt"
    with patch("shutil.move", lambda *_args, **_kwargs: None), patch.object(Path, "replace", lambda self, target: None):
        assert ErrorRecovery.safe_move(src, dst) is False

    src = tmp_path / "source2.txt"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "dest2.txt"
    with patch.object(Path, "stat", side_effect=[types.SimpleNamespace(st_size=1), RuntimeError("boom")]):
        assert ErrorRecovery.safe_move(src, dst, atomic=False) is False

    huge = tmp_path / "huge.txt"
    huge.write_text("x", encoding="utf-8")
    with patch.object(Path, "stat", return_value=types.SimpleNamespace(st_size=20 * 1024 * 1024)):
        assert ErrorRecovery.safe_read_text(huge, default="fallback", max_size_mb=1) == "fallback"

    @defensive_wrapper
    def check_value(_self, arg):
        raise RuntimeError("boom")

    @defensive_wrapper
    def get_value(_self, arg):
        raise RuntimeError("boom")

    @defensive_wrapper
    def do_value(_self, arg):
        raise RuntimeError("boom")

    assert check_value(object(), None) is False
    assert get_value(object(), None) is None
    with pytest.raises(RuntimeError):
        do_value(object(), None)


def test_doctor_recommended_actions_and_output_edges(monkeypatch, capsys):
    doc = doctor.UnpackrDoctor()
    doc.issues = ["Python version too old", "7-Zip not found", "No write permissions in current directory"]
    doc.warnings = ["par2cmdline not found - repair capability reduced", "ffmpeg version too old: 4.0 (need 4.4+)"]
    actions = doc._build_recommended_actions()
    assert any("Install Python 3.11+" in action for action in actions)
    assert any("7-Zip" in action for action in actions)
    assert any("permissions" in action for action in actions)

    doc.passed = ["Python version"]
    doc.print_header()
    doc.print_summary()
    out = capsys.readouterr().out
    assert "Unpackr Doctor - System Diagnostic" in out
    assert "Recommended Next Steps" in out


def test_doctor_version_and_process_check_edges(monkeypatch, tmp_path, capsys):
    doc = doctor.UnpackrDoctor()
    assert doc._extract_version_tuple("nothing") is None
    assert doc._format_version((1, 2, 3)) == "1.2.3"
    assert doc._is_version_at_least((1, 2), (1, 2, 0)) is True

    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(stdout="ffmpeg version 4.4.1", stderr=""),
    )
    assert doc._get_tool_version("ffmpeg", "ffmpeg") == (4, 4, 1)

    monkeypatch.setattr(doc, "_get_tool_version", lambda *_: None)
    doc._check_tool_min_version("ffmpeg", "ffmpeg", "ffmpeg", critical=False)
    assert any("version could not be detected" in warning for warning in doc.warnings)

    doc = doctor.UnpackrDoctor()
    monkeypatch.setattr(doc, "_get_tool_version", lambda *_: (4, 0, 0))
    doc._check_tool_min_version("ffmpeg", "ffmpeg", "ffmpeg", critical=False)
    assert any("version too old" in warning for warning in doc.warnings)

    monkeypatch.setattr(doctor.sys, "platform", "linux")
    doc = doctor.UnpackrDoctor()
    doc.check_running_processes()
    assert "Process check" in doc.passed

    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setattr(doctor.subprocess, "run", Mock(side_effect=RuntimeError("boom")))
    doc = doctor.UnpackrDoctor()
    doc.check_running_processes()
    assert "Could not check" in capsys.readouterr().out


def test_doctor_main_non_json(monkeypatch):
    monkeypatch.setattr(doctor.sys, "argv", ["unpackr-doctor"])

    class DummyDoctor:
        def __init__(self, config_path=None):
            self.config_path = config_path

        def run(self):
            return 0

    monkeypatch.setattr(doctor, "UnpackrDoctor", DummyDoctor)
    with pytest.raises(SystemExit) as exc:
        doctor.main()
    assert exc.value.code == 0
