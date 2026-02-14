from pathlib import Path

import pytest

import unpackr


def test_get_user_input_retries_until_valid(monkeypatch, tmp_path):
    bad = str(tmp_path / "missing")
    good = str(tmp_path)
    values = iter([bad, good])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(values))
    result = unpackr.get_user_input("path: ")
    assert result == tmp_path


def test_main_show_plan_exits_zero(monkeypatch, tmp_path):
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
    monkeypatch.setattr(unpackr.signal, "signal", lambda *_: None)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest), "--show-plan"])

    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 0


def test_main_exits_when_tool_status_blocked(monkeypatch, tmp_path):
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
            return {"7z": False, "par2": True, "ffmpeg": True}

        def display_tool_status(self, tools_status):
            return False

    monkeypatch.setattr(unpackr, "Config", lambda *_: DummyConfig())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(lambda p, **kwargs: Path(p)))
    monkeypatch.setattr(unpackr.StateValidator, "check_dir_writable", staticmethod(lambda *_: True))
    monkeypatch.setattr(unpackr.StateValidator, "check_disk_space", staticmethod(lambda *_args, **_kwargs: True))
    monkeypatch.setattr(unpackr, "SystemCheck", DummySystemCheck)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest)])

    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1


def test_main_exits_zero_when_process_conflict_abort(monkeypatch, tmp_path):
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
            return False

    monkeypatch.setattr(unpackr, "Config", lambda *_: DummyConfig())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(lambda p, **kwargs: Path(p)))
    monkeypatch.setattr(unpackr.StateValidator, "check_dir_writable", staticmethod(lambda *_: True))
    monkeypatch.setattr(unpackr.StateValidator, "check_disk_space", staticmethod(lambda *_args, **_kwargs: True))
    monkeypatch.setattr(unpackr, "SystemCheck", DummySystemCheck)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest)])

    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 0
