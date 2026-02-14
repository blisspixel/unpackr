"""Coverage-focused tests for unpackr doctor diagnostics."""

import builtins
import json
from pathlib import Path
import types

import pytest

import doctor


@pytest.fixture
def doc():
    return doctor.UnpackrDoctor()


def test_check_dependencies_missing_package(monkeypatch, doc, capsys):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(doctor, "__import__", fake_import, raising=False)
    doc.check_dependencies()
    out = capsys.readouterr().out
    assert "Missing: psutil" in out
    assert any("Missing packages" in i for i in doc.issues)


def test_check_config_file_missing_and_invalid_json(monkeypatch, doc, capsys, tmp_path):
    base = tmp_path / "repo"
    cfg_dir = base / "config_files"
    cfg_dir.mkdir(parents=True)

    monkeypatch.setattr(doctor, "__file__", str(base / "doctor.py"))
    doc.check_config_file()
    out = capsys.readouterr().out
    assert "Config file not found" in out

    (cfg_dir / "config.json").write_text("{bad json", encoding="utf-8")
    doc.issues = []
    doc.check_config_file()
    out = capsys.readouterr().out
    assert "Invalid JSON" in out
    assert "Config file has invalid JSON" in doc.issues


def test_check_config_file_valid_with_missing_keys_warns(monkeypatch, doc, capsys, tmp_path):
    base = tmp_path / "repo"
    cfg_dir = base / "config_files"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(json.dumps({"tool_paths": {}}), encoding="utf-8")
    monkeypatch.setattr(doctor, "__file__", str(base / "doctor.py"))

    doc.check_config_file()
    out = capsys.readouterr().out
    assert "Missing keys" in out
    assert any("Config missing keys" in w for w in doc.warnings)


def test_check_external_tools_paths(monkeypatch, doc, capsys, tmp_path):
    base = tmp_path / "repo"
    cfg_dir = base / "config_files"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"tool_paths": {"7z": ["7z"], "par2": ["par2"], "ffmpeg": ["ffmpeg"]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "__file__", str(base / "doctor.py"))

    def fake_check_tool(tool_name, commands, critical=True):
        if tool_name == "7z":
            return True, "7z"
        if tool_name == "par2":
            return False, None
        return False, None

    monkeypatch.setattr(doc, "check_tool", fake_check_tool)
    doc.check_external_tools()
    out = capsys.readouterr().out
    assert "7-Zip" in out
    assert any("par2cmdline not found" in w for w in doc.warnings)
    assert any("ffmpeg not found" in w for w in doc.warnings)


def test_check_write_permissions_failure(monkeypatch, doc, capsys):
    class DummyPath(Path):
        _flavour = type(Path())._flavour

        def write_text(self, *args, **kwargs):
            raise PermissionError("denied")

    monkeypatch.setattr(doctor, "Path", DummyPath)
    doc.check_write_permissions()
    out = capsys.readouterr().out
    assert "Cannot write" in out
    assert any("No write permissions" in i for i in doc.issues)


def test_check_disk_space_branches(monkeypatch, doc, capsys):
    fake_shutil = types.SimpleNamespace(disk_usage=lambda _: (100, 10, 11 * (2**30)))
    monkeypatch.setitem(__import__("sys").modules, "shutil", fake_shutil)
    doc.check_disk_space()
    out = capsys.readouterr().out
    assert "11GB available" in out

    fake_shutil.disk_usage = lambda _: (100, 10, 6 * (2**30))
    doc.warnings = []
    doc.check_disk_space()
    assert any("Only 6GB free" in w for w in doc.warnings)

    fake_shutil.disk_usage = lambda _: (100, 10, 4 * (2**30))
    doc.issues = []
    doc.check_disk_space()
    assert any("Only 4GB free" in i for i in doc.issues)


def test_check_comments_file_variants(monkeypatch, doc, capsys, tmp_path):
    base = tmp_path / "repo"
    cfg_dir = base / "config_files"
    cfg_dir.mkdir(parents=True)
    monkeypatch.setattr(doctor, "__file__", str(base / "doctor.py"))

    doc.check_comments_file()
    assert any("No comments.json" in w for w in doc.warnings)

    (cfg_dir / "comments.json").write_text(json.dumps({"comments": ["a", "b"]}), encoding="utf-8")
    doc.warnings = []
    doc.passed = []
    doc.check_comments_file()
    out = capsys.readouterr().out
    assert "2 comments loaded" in out
    assert "Easter egg comments" in doc.passed

    (cfg_dir / "comments.json").write_text("{bad", encoding="utf-8")
    doc.warnings = []
    doc.check_comments_file()
    assert any("invalid json" in w.lower() for w in doc.warnings)


def test_check_core_modules_missing(monkeypatch, doc, capsys):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "core.video_processor":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(doctor, "__import__", fake_import, raising=False)
    doc.check_core_modules()
    out = capsys.readouterr().out
    assert "Missing:" in out
    assert any("Missing modules:" in i for i in doc.issues)


def test_check_log_directory_failure(monkeypatch, doc, capsys):
    class DummyPath(Path):
        _flavour = type(Path())._flavour

        def mkdir(self, *args, **kwargs):
            raise OSError("nope")

    monkeypatch.setattr(doctor, "Path", DummyPath)
    doc.check_log_directory()
    out = capsys.readouterr().out
    assert "Cannot create" in out
    assert any("Cannot create log directory" in i for i in doc.issues)


def test_check_running_processes_windows_conflicts(monkeypatch, doc, capsys):
    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(stdout="7z.exe\npar2.exe\n"),
    )
    doc.check_running_processes()
    out = capsys.readouterr().out
    assert "Running: 7-Zip, par2" in out


def test_print_summary_and_run(monkeypatch, doc, capsys):
    doc.passed = ["A", "B"]
    doc.warnings = ["W1"]
    doc.issues = ["I1"]
    doc.print_summary()
    out = capsys.readouterr().out
    assert "Summary" in out
    assert "BLOCKED" in out
    assert "Critical Issues" in out

    ordered = []
    for name in [
        "print_header",
        "check_python_version",
        "check_dependencies",
        "check_config_file",
        "check_external_tools",
        "check_write_permissions",
        "check_disk_space",
        "check_comments_file",
        "check_core_modules",
        "check_log_directory",
        "check_running_processes",
        "print_summary",
    ]:
        monkeypatch.setattr(doc, name, lambda n=name: ordered.append(n))

    doc.issues = []
    assert doc.run() == 0
    assert ordered[0] == "print_header"
    assert ordered[-1] == "print_summary"
