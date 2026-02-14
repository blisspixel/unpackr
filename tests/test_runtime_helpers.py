"""Tests for runtime helper behavior in unpackr and CLI bootstrap."""

import io
import shutil

import unpackr
from utils import cli_runtime


def test_quick_preflight_returns_true_when_no_warnings(monkeypatch, tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    (source / "file.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(shutil, "disk_usage", lambda *_: (100, 10, 20 * (2**30)))
    monkeypatch.setattr("builtins.input", lambda: "n")

    assert unpackr.quick_preflight(object(), source, dest) is True


def test_quick_preflight_aborts_on_warning_and_no_confirmation(monkeypatch, tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()

    # Low disk and empty source trigger warnings -> confirmation prompt.
    monkeypatch.setattr(shutil, "disk_usage", lambda *_: (100, 10, 4 * (2**30)))
    monkeypatch.setattr("builtins.input", lambda: "n")

    assert unpackr.quick_preflight(object(), source, dest) is False


def test_quick_preflight_handles_eof_as_abort(monkeypatch, tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()

    monkeypatch.setattr(shutil, "disk_usage", lambda *_: (100, 10, 4 * (2**30)))

    def raise_eof():
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert unpackr.quick_preflight(object(), source, dest) is False


def test_countdown_prompt_returns_true_when_sleep_succeeds(monkeypatch):
    monkeypatch.setattr(unpackr.time, "sleep", lambda *_: None)
    assert unpackr.countdown_prompt(1, operation_label="test-run") is True


def test_countdown_prompt_returns_false_on_keyboard_interrupt(monkeypatch):
    def raise_interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(unpackr.time, "sleep", raise_interrupt)
    assert unpackr.countdown_prompt(1) is False


def test_cli_runtime_parser_handles_named_and_flags():
    parser = cli_runtime.build_unpackr_arg_parser()
    args = parser.parse_args(
        ["--source", "A", "--destination", "B", "--dry-run", "--vhealth", "--animations", "light", "--no-color"]
    )
    assert args.source == "A"
    assert args.destination == "B"
    assert args.dry_run is True
    assert args.vhealth is True
    assert args.animations == "light"
    assert args.no_color is True


def test_resolve_cli_presentation_cli_precedence_over_env_and_config(monkeypatch):
    config = unpackr.Config(None)
    config.set("animations", "off")
    config.set("no_color", False)
    args = type("Args", (), {"animations": "full", "no_color": True})()
    monkeypatch.setenv("UNPACKR_ANIMATIONS", "light")
    monkeypatch.setenv("UNPACKR_NO_COLOR", "0")

    mode, no_color = unpackr.resolve_cli_presentation(args, config)
    assert mode == "full"
    assert no_color is True


def test_resolve_cli_presentation_env_then_config(monkeypatch):
    config = unpackr.Config(None)
    config.set("animations", "off")
    config.set("no_color", False)
    args = type("Args", (), {"animations": None, "no_color": False})()
    monkeypatch.setenv("UNPACKR_ANIMATIONS", "light")
    monkeypatch.setenv("UNPACKR_NO_COLOR", "1")

    mode, no_color = unpackr.resolve_cli_presentation(args, config)
    assert mode == "light"
    assert no_color is True


def test_resolve_cli_presentation_normalizes_case(monkeypatch):
    config = unpackr.Config(None)
    config.set("animations", "FULL")
    config.set("no_color", False)
    args = type("Args", (), {"animations": None, "no_color": False})()
    monkeypatch.setenv("UNPACKR_ANIMATIONS", "LiGhT")
    monkeypatch.setenv("UNPACKR_NO_COLOR", "TrUe")
    monkeypatch.delenv("NO_COLOR", raising=False)

    mode, no_color = unpackr.resolve_cli_presentation(args, config)
    assert mode == "light"
    assert no_color is True


def test_resolve_cli_presentation_config_fallback(monkeypatch):
    config = unpackr.Config(None)
    config.set("animations", "full")
    config.set("no_color", True)
    args = type("Args", (), {"animations": None, "no_color": False})()
    monkeypatch.delenv("UNPACKR_ANIMATIONS", raising=False)
    monkeypatch.delenv("UNPACKR_NO_COLOR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)

    mode, no_color = unpackr.resolve_cli_presentation(args, config)
    assert mode == "full"
    assert no_color is True


def test_resolve_cli_presentation_handles_missing_arg_fields(monkeypatch):
    config = unpackr.Config(None)
    config.set("animations", "light")
    config.set("no_color", False)
    args = object()
    monkeypatch.delenv("UNPACKR_ANIMATIONS", raising=False)
    monkeypatch.delenv("UNPACKR_NO_COLOR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)

    mode, no_color = unpackr.resolve_cli_presentation(args, config)
    assert mode == "light"
    assert no_color is False


def test_configure_windows_console_utf8_uses_reconfigure_branch(monkeypatch):
    calls = {"stdout": None, "stderr": None, "system": None}

    class DummyStream:
        def __init__(self, name):
            self.name = name
            self.buffer = io.BytesIO()

        def reconfigure(self, encoding=None):
            calls[self.name] = encoding

    monkeypatch.setattr(cli_runtime.sys, "platform", "win32")
    monkeypatch.setattr(cli_runtime.sys, "stdout", DummyStream("stdout"))
    monkeypatch.setattr(cli_runtime.sys, "stderr", DummyStream("stderr"))
    monkeypatch.setattr(cli_runtime.os, "system", lambda cmd: calls.__setitem__("system", cmd) or 0)

    cli_runtime.configure_windows_console_utf8()

    assert calls["stdout"] == "utf-8"
    assert calls["stderr"] == "utf-8"
    assert "chcp 65001" in calls["system"]


def test_configure_windows_console_utf8_swallow_errors(monkeypatch):
    class BadStream:
        def reconfigure(self, encoding=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(cli_runtime.sys, "platform", "win32")
    monkeypatch.setattr(cli_runtime.sys, "stdout", BadStream())
    monkeypatch.setattr(cli_runtime.sys, "stderr", BadStream())

    # Should not raise
    cli_runtime.configure_windows_console_utf8()


def test_configure_windows_console_utf8_non_windows_noop(monkeypatch):
    monkeypatch.setattr(cli_runtime.sys, "platform", "linux")
    cli_runtime.configure_windows_console_utf8()


def test_configure_windows_console_utf8_codecs_writer_fallback(monkeypatch):
    class StreamNoReconfigure:
        def __init__(self):
            self.buffer = io.BytesIO()

    calls = {"cmd": None}
    monkeypatch.setattr(cli_runtime.sys, "platform", "win32")
    monkeypatch.setattr(cli_runtime.sys, "stdout", StreamNoReconfigure())
    monkeypatch.setattr(cli_runtime.sys, "stderr", StreamNoReconfigure())
    monkeypatch.setattr(cli_runtime.os, "system", lambda cmd: calls.__setitem__("cmd", cmd) or 0)

    cli_runtime.configure_windows_console_utf8()

    assert calls["cmd"] is not None
    assert hasattr(cli_runtime.sys.stdout, "write")
