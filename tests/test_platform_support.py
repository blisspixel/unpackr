"""Cross-platform helper regression tests."""

from pathlib import Path

import pytest

from utils import platform_support


def test_default_tool_candidates_put_path_names_first():
    seven = platform_support.default_tool_candidates("7z")
    assert seven[0] in {"7z", "7zz", "7za"}
    assert "7z" in seven


def test_merge_tool_candidates_preserves_configured_priority():
    merged = platform_support.merge_tool_candidates([r"C:\custom\7z.exe", "7z"], "7z")
    assert merged[0] == r"C:\custom\7z.exe"
    assert "7z" in merged


def test_merge_tool_candidates_handles_malformed_config():
    assert platform_support.merge_tool_candidates(None, "ffmpeg")[0] == "ffmpeg"
    assert platform_support.merge_tool_candidates(123, "ffmpeg")[0] == "ffmpeg"
    assert platform_support.merge_tool_candidates(["ffmpeg", 7, ""], "ffmpeg")[0] == "ffmpeg"


def test_build_powershell_delete_command_encodes_path_as_data(tmp_path):
    folder = tmp_path / "folder with 'quote' and $meta"
    command = platform_support.build_powershell_delete_command(folder)
    assert command[:3] == ["powershell", "-NoProfile", "-EncodedCommand"]
    assert len(command[3]) > 20


def test_force_delete_directory_posix_style(tmp_path, monkeypatch):
    target = tmp_path / "nested"
    nested = target / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    assert platform_support.force_delete_directory(target) is True
    assert not target.exists()


def test_force_delete_directory_refuses_symlink_root(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable on this host")

    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    assert platform_support.force_delete_directory(link) is False
    assert real.exists()


def test_detect_running_helpers_uses_platform_detection(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    monkeypatch.setattr(
        platform_support.subprocess,
        "run",
        lambda *args, **kwargs: type("R", (), {"stdout": "root 1 0.0 0.0 7z\n"})(),
    )
    # Force the psutil path to fail so subprocess fallback is used.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("forced")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    found = platform_support.detect_running_helpers(["7-Zip", "par2"])
    assert "7-Zip" in found


def test_kill_helper_processes_posix_uses_exact_pkill(monkeypatch):
    calls = []
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(platform_support.subprocess, "run", fake_run)
    assert platform_support.kill_helper_processes(["7-Zip", "par2"]) is True
    assert any(cmd[:3] == ["pkill", "-9", "-x"] for cmd in calls)


def test_example_paths_are_non_empty():
    assert platform_support.example_source_path()
    assert platform_support.example_destination_path()
    assert platform_support.platform_label()
