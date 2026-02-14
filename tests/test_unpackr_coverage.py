"""Coverage-focused tests for unpackr internals and main flow branches."""

from pathlib import Path
import types

import pytest

import unpackr


def test_remove_sample_videos_deletes_matching_sample(tmp_path):
    sample = tmp_path / "movie.sample.mkv"
    full = tmp_path / "movie.1080p.mkv"
    sample.write_bytes(b"x" * (1 * 1024 * 1024))
    full.write_bytes(b"x" * (5 * 1024 * 1024))

    dummy = types.SimpleNamespace(
        stats={"videos_sample": 0},
        dry_run=False,
        dry_run_plan=None,
    )

    result = unpackr.UnpackrApp._remove_sample_videos(dummy, [sample, full])
    assert full in result
    assert sample not in result
    assert not sample.exists()
    assert dummy.stats["videos_sample"] == 1


def test_remove_sample_videos_dry_run_uses_plan(tmp_path):
    sample = tmp_path / "movie.sample.mkv"
    full = tmp_path / "movie.1080p.mkv"
    sample.write_bytes(b"x" * (1 * 1024 * 1024))
    full.write_bytes(b"x" * (5 * 1024 * 1024))

    seen = {}

    class Plan:
        def add_video_delete(self, path, reason):
            seen["path"] = path
            seen["reason"] = reason

    dummy = types.SimpleNamespace(
        stats={"videos_sample": 0},
        dry_run=True,
        dry_run_plan=Plan(),
    )

    result = unpackr.UnpackrApp._remove_sample_videos(dummy, [sample, full])
    assert full in result
    assert sample not in result
    assert sample.exists()  # dry-run should not delete
    assert seen["path"] == sample
    assert "sample/preview" in seen["reason"]


def test_load_comments_copies_sample_file_on_first_run(monkeypatch, tmp_path):
    base = tmp_path / "repo"
    config_dir = base / "config_files"
    config_dir.mkdir(parents=True)
    sample = config_dir / "comments.sample.json"
    sample.write_text('{"comments": ["hello"]}', encoding="utf-8")

    monkeypatch.setattr(unpackr, "__file__", str(base / "unpackr.py"))
    dummy = types.SimpleNamespace()

    loaded = unpackr.UnpackrApp._load_comments(dummy)
    assert loaded == ["hello"]
    assert (config_dir / "comments.json").exists()


def test_get_random_comment_old_format_persists(monkeypatch):
    monkeypatch.setattr(unpackr.random, "choice", lambda seq: seq[0])
    dummy = types.SimpleNamespace(
        comments=["one", "two"],
        last_comment_folder=-10,
        current_comment_display=None,
    )

    first = unpackr.UnpackrApp._get_random_comment(dummy, 1)
    second = unpackr.UnpackrApp._get_random_comment(dummy, 1)
    cooldown = unpackr.UnpackrApp._get_random_comment(dummy, 2)

    assert first == second
    assert cooldown is None


def test_main_exits_when_setup_logging_fails(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()

    class DummyConfig:
        log_folder = "logs"
        max_log_files = 3

    monkeypatch.setattr(unpackr, "Config", lambda *_: DummyConfig())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: (_ for _ in ()).throw(RuntimeError("log fail")))
    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(lambda p, **kwargs: Path(p)))
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest)])

    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1


def test_main_exits_when_quick_preflight_fails(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()

    class DummyConfig:
        log_folder = "logs"
        max_log_files = 3

    class DummySystemCheck:
        def __init__(self, config):
            pass

        def check_all_tools(self):
            return {"7z": True, "par2": True, "ffmpeg": True}

        def display_tool_status(self, tools_status):
            return True

        def warn_running_processes(self):
            return True

    class DummyWorkPlan:
        video_folders = []

        def display(self):
            pass

        def display_detailed(self):
            pass

    class DummyApp:
        def __init__(self, config):
            self.cancellation_requested = False
            self.active_process = None
            self.dry_run = False
            self.dry_run_plan = None

        def _stop_spinner_thread(self):
            pass

        def scan_and_plan(self, source_dir):
            return DummyWorkPlan()

    monkeypatch.setattr(unpackr, "Config", lambda *_: DummyConfig())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(lambda p, **kwargs: Path(p)))
    monkeypatch.setattr(unpackr.StateValidator, "check_dir_writable", staticmethod(lambda *_: True))
    monkeypatch.setattr(unpackr.StateValidator, "check_disk_space", staticmethod(lambda *_args, **_kwargs: True))
    monkeypatch.setattr(unpackr, "SystemCheck", DummySystemCheck)
    monkeypatch.setattr(unpackr, "UnpackrApp", DummyApp)
    monkeypatch.setattr(unpackr, "quick_preflight", lambda *_: False)
    monkeypatch.setattr(unpackr.signal, "signal", lambda *_: None)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest)])

    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1


def test_main_exits_zero_when_countdown_cancelled(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()

    class DummyConfig:
        log_folder = "logs"
        max_log_files = 3

    class DummySystemCheck:
        def __init__(self, config):
            pass

        def check_all_tools(self):
            return {"7z": True, "par2": True, "ffmpeg": True}

        def display_tool_status(self, tools_status):
            return True

        def warn_running_processes(self):
            return True

    class DummyWorkPlan:
        video_folders = []

        def display(self):
            pass

        def display_detailed(self):
            pass

    class DummyApp:
        def __init__(self, config):
            self.cancellation_requested = False
            self.active_process = None
            self.dry_run = False
            self.dry_run_plan = None

        def _stop_spinner_thread(self):
            pass

        def scan_and_plan(self, source_dir):
            return DummyWorkPlan()

    monkeypatch.setattr(unpackr, "Config", lambda *_: DummyConfig())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(lambda p, **kwargs: Path(p)))
    monkeypatch.setattr(unpackr.StateValidator, "check_dir_writable", staticmethod(lambda *_: True))
    monkeypatch.setattr(unpackr.StateValidator, "check_disk_space", staticmethod(lambda *_args, **_kwargs: True))
    monkeypatch.setattr(unpackr, "SystemCheck", DummySystemCheck)
    monkeypatch.setattr(unpackr, "UnpackrApp", DummyApp)
    monkeypatch.setattr(unpackr, "quick_preflight", lambda *_: True)
    monkeypatch.setattr(unpackr, "countdown_prompt", lambda *_, **__: False)
    monkeypatch.setattr(unpackr.signal, "signal", lambda *_: None)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest)])

    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 0

