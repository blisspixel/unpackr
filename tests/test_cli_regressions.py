"""CLI-level regression tests for high-impact runtime behaviors."""

from argparse import Namespace
from pathlib import Path
import sys
import types

import pytest
import vhealth
import unpackr


def test_vhealth_main_default_is_not_auto_delete(monkeypatch, tmp_path):
    """`vhealth <path>` should not force auto-delete without flags."""
    target = tmp_path / "videos"
    target.mkdir()

    args = Namespace(
        path=str(target),
        clean=False,
        delete_bad=False,
        min_resolution=None,
        skip_samples=False,
        config=None,
        verbose=False,
    )

    calls = {}

    class DummyChecker:
        def __init__(self, config):
            calls["config"] = config

        def check_path(self, path, **kwargs):
            calls["path"] = path
            calls["check_kwargs"] = kwargs

        def print_summary(self, auto_delete=False):
            calls["summary_auto_delete"] = auto_delete

    monkeypatch.setattr(vhealth.argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(vhealth, "VideoHealthChecker", DummyChecker)
    monkeypatch.setattr(vhealth, "Config", lambda config_path=None: object())
    monkeypatch.setattr("time.sleep", lambda *_: None)

    vhealth.main()

    assert calls["path"] == target
    assert calls["check_kwargs"]["delete_bad"] is False
    assert calls["summary_auto_delete"] is False


def test_vhealth_main_passes_config_path(monkeypatch, tmp_path):
    """`--config` should call Config with the config path argument."""
    target = tmp_path / "videos"
    target.mkdir()
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")

    args = Namespace(
        path=str(target),
        clean=False,
        delete_bad=False,
        min_resolution=None,
        skip_samples=False,
        config=str(cfg),
        verbose=False,
    )

    seen = {}

    class DummyChecker:
        def __init__(self, config):
            pass

        def check_path(self, path, **kwargs):
            pass

        def print_summary(self, auto_delete=False):
            pass

    def fake_config(config_path=None):
        seen["config_path"] = config_path
        return object()

    monkeypatch.setattr(vhealth.argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(vhealth, "VideoHealthChecker", DummyChecker)
    monkeypatch.setattr(vhealth, "Config", fake_config)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    vhealth.main()

    assert seen["config_path"] == cfg


def test_vhealth_main_handles_inaccessible_path(monkeypatch):
    """Path access errors should produce a clean SystemExit instead of traceback."""
    args = Namespace(
        path="G:/locked",
        clean=False,
        delete_bad=False,
        min_resolution=None,
        skip_samples=False,
        config=None,
        verbose=False,
    )

    monkeypatch.setattr(vhealth.argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(vhealth, "Config", lambda config_path=None: object())
    monkeypatch.setattr(vhealth.Path, "exists", lambda self: (_ for _ in ()).throw(OSError("locked")))

    with pytest.raises(SystemExit) as exc:
        vhealth.main()
    assert exc.value.code == 1


def test_unpackr_main_vhealth_uses_destination_dir(monkeypatch, tmp_path):
    """`unpackr --vhealth` should pass destination_dir to vhealth checker."""
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()

    seen = {}

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

        def cleanup_empty_folders(self, *args, **kwargs):
            pass

        def run(self, source_dir, destination_dir):
            pass

        def retry_failed_deletions(self):
            pass

        def display_summary(self):
            pass

    class DummyChecker:
        def __init__(self, config):
            pass

        def check_path(self, path, **kwargs):
            seen["vhealth_path"] = path

        def print_summary(self, auto_delete=False):
            seen["auto_delete"] = auto_delete

    monkeypatch.setattr(unpackr, "Config", lambda config_path=None: DummyConfig())
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr.InputValidator, "validate_path", staticmethod(lambda p, **kwargs: Path(p)))
    monkeypatch.setattr(unpackr.StateValidator, "check_dir_writable", staticmethod(lambda *_: True))
    monkeypatch.setattr(unpackr.StateValidator, "check_disk_space", staticmethod(lambda *_args, **_kwargs: True))
    monkeypatch.setattr(unpackr, "SystemCheck", DummySystemCheck)
    monkeypatch.setattr(unpackr, "UnpackrApp", DummyApp)
    monkeypatch.setattr(unpackr, "quick_preflight", lambda *_: True)
    monkeypatch.setattr(unpackr, "countdown_prompt", lambda *_: True)
    monkeypatch.setattr(unpackr.signal, "signal", lambda *_: None)
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest), "--vhealth"])
    monkeypatch.setitem(sys.modules, "vhealth", types.SimpleNamespace(VideoHealthChecker=DummyChecker))

    unpackr.main()

    assert seen["vhealth_path"] == dest
    assert seen["auto_delete"] is False
