from pathlib import Path
import sys
import types

import pytest

import unpackr


class _Cfg:
    log_folder = "logs"
    max_log_files = 3


class _SystemCheckOK:
    def __init__(self, config):
        pass

    def check_all_tools(self):
        return {"7z": True, "par2": True, "ffmpeg": True}

    def display_tool_status(self, _status):
        return True

    def warn_running_processes(self):
        return True


class _WorkPlan:
    def __init__(self, n=0):
        self.video_folders = [{}] * n

    def display(self):
        pass

    def display_detailed(self):
        pass


def _base_monkeypatch(monkeypatch, tmp_path, source, dest):
    monkeypatch.setattr(unpackr, "Config", lambda *_: _Cfg())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(lambda p, **kwargs: Path(p)))
    monkeypatch.setattr(unpackr.StateValidator, "check_dir_writable", staticmethod(lambda *_: True))
    monkeypatch.setattr(unpackr.StateValidator, "check_disk_space", staticmethod(lambda *_a, **_k: True))
    monkeypatch.setattr(unpackr, "SystemCheck", _SystemCheckOK)
    monkeypatch.setattr(unpackr, "quick_preflight", lambda *_: True)
    monkeypatch.setattr(unpackr, "countdown_prompt", lambda *_a, **_k: True)
    monkeypatch.setattr(unpackr.signal, "signal", lambda *_: None)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest)])


def test_main_path_validation_error_branch(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()
    _base_monkeypatch(monkeypatch, tmp_path, source, dest)

    def raise_validation(path, **kwargs):
        raise unpackr.ValidationError("bad path")

    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(raise_validation))
    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1


def test_main_interactive_and_not_writable_branch(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()

    monkeypatch.setattr(unpackr, "Config", lambda *_: _Cfg())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr, "SystemCheck", _SystemCheckOK)
    monkeypatch.setattr(unpackr, "quick_preflight", lambda *_: True)
    monkeypatch.setattr(unpackr, "countdown_prompt", lambda *_a, **_k: True)
    monkeypatch.setattr(unpackr.signal, "signal", lambda *_: None)
    monkeypatch.setattr(unpackr.StateValidator, "check_dir_writable", staticmethod(lambda *_: False))
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr"])
    values = iter([source, dest])
    monkeypatch.setattr(unpackr, "get_user_input", lambda *_: next(values))

    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1


def test_main_app_init_and_scan_failure_branches(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()
    _base_monkeypatch(monkeypatch, tmp_path, source, dest)

    monkeypatch.setattr(unpackr, "UnpackrApp", lambda *_: (_ for _ in ()).throw(RuntimeError("init boom")))
    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1

    class AppScanBoom:
        def __init__(self, cfg):
            self.cancellation_requested = False
            self.active_process = None
            self.dry_run = False
            self.dry_run_plan = None

        def _stop_spinner_thread(self):
            pass

        def scan_and_plan(self, _src):
            raise RuntimeError("scan boom")

    monkeypatch.setattr(unpackr, "UnpackrApp", AppScanBoom)
    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1


def test_main_cleanup_warning_and_vhealth_exception(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()
    _base_monkeypatch(monkeypatch, tmp_path, source, dest)
    monkeypatch.setattr(unpackr.StateValidator, "check_disk_space", staticmethod(lambda *_a, **_k: False))

    class App:
        def __init__(self, cfg):
            self.cancellation_requested = False
            self.active_process = None
            self.dry_run = False
            self.dry_run_plan = None
            self.cleanup_calls = 0

        def _stop_spinner_thread(self):
            pass

        def scan_and_plan(self, _src):
            return _WorkPlan(n=1)

        def cleanup_empty_folders(self, *_a, **_k):
            self.cleanup_calls += 1
            if self.cleanup_calls == 1:
                raise RuntimeError("cleanup boom")

        def run(self, *_a, **_k):
            pass

        def retry_failed_deletions(self):
            pass

        def display_summary(self):
            pass

    class BadChecker:
        def __init__(self, config):
            pass

        def check_path(self, *args, **kwargs):
            raise RuntimeError("vhealth boom")

        def print_summary(self, auto_delete=False):
            pass

    monkeypatch.setattr(unpackr, "UnpackrApp", App)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest), "--vhealth"])
    monkeypatch.setitem(sys.modules, "vhealth", types.SimpleNamespace(VideoHealthChecker=BadChecker))

    # Should complete without fatal exit despite cleanup warning + vhealth exception.
    unpackr.main()


def test_main_processing_fatal_exception_branch(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()
    _base_monkeypatch(monkeypatch, tmp_path, source, dest)

    class AppFatal:
        def __init__(self, cfg):
            self.cancellation_requested = False
            self.active_process = None
            self.dry_run = False
            self.dry_run_plan = None

        def _stop_spinner_thread(self):
            pass

        def scan_and_plan(self, _src):
            return _WorkPlan(n=60)  # skip-initial-cleanup branch

        def run(self, *_a, **_k):
            raise RuntimeError("run boom")

        def display_summary(self):
            pass

    monkeypatch.setattr(unpackr, "UnpackrApp", AppFatal)
    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1
