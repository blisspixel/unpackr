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


def test_package_manager_hints_are_platform_specific(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: True)
    monkeypatch.setattr(platform_support, "is_macos", lambda: False)
    monkeypatch.setattr(platform_support, "is_linux", lambda: False)
    assert "7-Zip" in platform_support.package_manager_install_hint()

    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    monkeypatch.setattr(platform_support, "is_macos", lambda: True)
    assert "brew install" in platform_support.package_manager_install_hint()

    monkeypatch.setattr(platform_support, "is_macos", lambda: False)
    monkeypatch.setattr(platform_support, "is_linux", lambda: True)
    hint = platform_support.package_manager_install_hint()
    assert "apt" in hint and "dnf" in hint


def test_tool_missing_hint_mentions_tool_and_recipe(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    monkeypatch.setattr(platform_support, "is_macos", lambda: False)
    monkeypatch.setattr(platform_support, "is_linux", lambda: True)
    hint = platform_support.tool_missing_hint("7z")
    assert "7z" in hint.lower() or "p7zip" in hint.lower()
    assert "apt" in hint


def test_resolve_first_available_tool_prefers_existing_absolute(tmp_path):
    tool = tmp_path / "7z-custom"
    tool.write_text("", encoding="utf-8")
    # On Windows executables often need .exe; we only require is_file().
    found = platform_support.resolve_first_available_tool("7z", [str(tool), "7z"])
    assert found == str(tool)


def test_shell_launchers_exist_and_are_posix_scripts():
    root = Path(__file__).parents[1]
    for name in ("unpackr.sh", "unpackr-doctor.sh", "vhealth.sh"):
        path = root / name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash")
        assert "python3" in text


def test_default_tool_candidates_macos_appends_homebrew_paths(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    monkeypatch.setattr(platform_support, "is_macos", lambda: True)
    candidates = platform_support.default_tool_candidates("ffmpeg")
    assert "ffmpeg" in candidates
    # Path joins use OS separators; match either form.
    assert any(path.replace("\\", "/").endswith("/ffmpeg") for path in candidates)


def test_default_tool_candidates_windows_appends_program_files(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: True)
    candidates = platform_support.default_tool_candidates("7z")
    assert any("Program Files" in path for path in candidates)


def test_resolve_first_available_tool_rejects_relative_paths_and_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    monkeypatch.setattr(platform_support, "is_macos", lambda: False)
    monkeypatch.setattr(platform_support.shutil, "which", lambda name: None)
    assert platform_support.resolve_first_available_tool("7z", ["./relative/7z", "missing-cmd"]) == ""
    assert platform_support.resolve_first_available_tool("7z", [str(tmp_path / "nope.exe")]) == ""


def test_resolve_first_available_tool_uses_path_lookup(monkeypatch):
    monkeypatch.setattr(platform_support.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    assert platform_support.resolve_first_available_tool("ffmpeg", ["ffmpeg"]) == "/usr/bin/ffmpeg"


def test_force_delete_missing_path_is_success(tmp_path):
    missing = tmp_path / "gone"
    assert platform_support.force_delete_directory(missing) is True


def test_force_delete_windows_path_uses_powershell(tmp_path, monkeypatch):
    target = tmp_path / "win-del"
    target.mkdir()
    (target / "a.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(platform_support, "is_windows", lambda: True)

    def fake_run(cmd, **kwargs):
        # Simulate PowerShell removing the tree.
        import shutil

        shutil.rmtree(target, ignore_errors=True)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(platform_support.subprocess, "run", fake_run)
    assert platform_support.force_delete_directory(target) is True
    assert not target.exists()


def test_force_delete_windows_timeout_returns_false(tmp_path, monkeypatch):
    target = tmp_path / "win-timeout"
    target.mkdir()
    monkeypatch.setattr(platform_support, "is_windows", lambda: True)

    def boom(*args, **kwargs):
        raise platform_support.subprocess.TimeoutExpired(cmd="powershell", timeout=1)

    monkeypatch.setattr(platform_support.subprocess, "run", boom)
    assert platform_support.force_delete_directory(target) is False
    assert target.exists()


def test_detect_running_helpers_windows_tasklist(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: True)

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "tasklist"
        return type("R", (), {"stdout": '"ffmpeg.exe","1234","Console"\n'})()

    monkeypatch.setattr(platform_support.subprocess, "run", fake_run)
    found = platform_support.detect_running_helpers(["ffmpeg", "par2"])
    assert found == ["ffmpeg"]


def test_detect_running_helpers_empty_labels_returns_empty(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    assert platform_support.detect_running_helpers([]) == []


def test_detect_running_helpers_oserror_returns_empty(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: True)

    def boom(*args, **kwargs):
        raise OSError("no tasklist")

    monkeypatch.setattr(platform_support.subprocess, "run", boom)
    assert platform_support.detect_running_helpers(["7-Zip"]) == []


def test_kill_helper_processes_windows_taskkill(monkeypatch):
    calls = []
    monkeypatch.setattr(platform_support, "is_windows", lambda: True)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(platform_support.subprocess, "run", fake_run)
    assert platform_support.kill_helper_processes(["7-Zip", "par2", "ffmpeg"]) is True
    assert any(cmd[:3] == ["taskkill", "/F", "/IM"] for cmd in calls)


def test_kill_helper_processes_exception_returns_false(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)

    def boom(*args, **kwargs):
        raise RuntimeError("pkill missing")

    monkeypatch.setattr(platform_support.subprocess, "run", boom)
    assert platform_support.kill_helper_processes(["ffmpeg"]) is False


def test_platform_label_unknown(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    monkeypatch.setattr(platform_support, "is_macos", lambda: False)
    monkeypatch.setattr(platform_support, "is_linux", lambda: False)
    monkeypatch.setattr(platform_support.sys, "platform", "aix")
    assert platform_support.platform_label() == "aix"


def test_package_manager_hint_unknown_platform(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    monkeypatch.setattr(platform_support, "is_macos", lambda: False)
    monkeypatch.setattr(platform_support, "is_linux", lambda: False)
    assert "package manager" in platform_support.package_manager_install_hint().lower()


def test_helper_process_names_windows_and_posix(monkeypatch):
    monkeypatch.setattr(platform_support, "is_windows", lambda: True)
    assert "7z.exe" in platform_support.helper_process_names()["7-Zip"]
    monkeypatch.setattr(platform_support, "is_windows", lambda: False)
    assert "7zz" in platform_support.helper_process_names()["7-Zip"]
