import json
from core.config import Config
from utils.system_check import SystemCheck


def test_system_check_rejects_relative_filesystem_tool_path(monkeypatch):
    checker = SystemCheck(config={"tool_paths": {"par2": [r"bin\par2.exe", "par2"]}})

    def fake_which(cmd):
        if cmd == "par2":
            return r"C:\Program Files\par2cmdline\par2.exe"
        return None

    monkeypatch.setattr("utils.system_check.shutil.which", fake_which)

    assert checker._resolve_tool_path(r"bin\par2.exe") == ""
    assert checker.get_tool_command("par2") == [r"C:\Program Files\par2cmdline\par2.exe"]


def test_system_check_check_tool_never_executes_relative_filesystem_tool_path(monkeypatch):
    checker = SystemCheck(config={"tool_paths": {"par2": [r"bin\par2.exe", "par2"]}})
    calls = []

    def fake_which(cmd):
        if cmd == "par2":
            return r"C:\Program Files\par2cmdline\par2.exe"
        return None

    def fake_run(command, **kwargs):
        calls.append(command)
        return object()

    monkeypatch.setattr("utils.system_check.shutil.which", fake_which)
    monkeypatch.setattr("utils.system_check.subprocess.run", fake_run)

    assert checker.check_tool("par2") is True
    assert calls == [[r"C:\Program Files\par2cmdline\par2.exe"]]


def test_config_validate_tool_paths_rejects_relative_filesystem_executable(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"tool_paths": {"par2": [r"bin\par2.exe", "par2"]}}), encoding="utf-8")

    config = Config(config_path)
    ok, errors = config.validate_tool_paths()

    assert ok is False
    assert any("unsafe relative executable path" in error for error in errors)


def test_system_check_prefers_path_resolution_for_default_command(monkeypatch):
    checker = SystemCheck()
    monkeypatch.setattr("utils.system_check.shutil.which", lambda cmd: r"C:\tools\par2.exe" if cmd == "par2" else None)

    assert checker.get_tool_command("par2") == [r"C:\tools\par2.exe"]


def test_system_check_tolerates_malformed_tool_paths(monkeypatch):
    """Malformed tool_paths shapes must not crash discovery."""
    resolved = r"C:\tools\7z.exe"
    monkeypatch.setattr("utils.system_check.shutil.which", lambda cmd: resolved if cmd == "7z" else None)
    monkeypatch.setattr("utils.system_check.subprocess.run", lambda *args, **kwargs: object())

    for bad in (123, True, {"nested": "value"}, [7, None, "7z"]):
        checker = SystemCheck(config={"tool_paths": {"7z": bad}})
        assert checker.check_tool("7z") is True
        assert checker.get_tool_command("7z") == [resolved]

    checker = SystemCheck(config={"tool_paths": "not-a-dict"})
    assert checker.check_tool("7z") is True
    assert checker.get_tool_command("7z") == [resolved]


def test_system_check_rejects_relative_7z_command_for_extraction(monkeypatch):
    checker = SystemCheck(config={"tool_paths": {"7z": [r".\7z.exe", "7z"]}})

    def fake_which(cmd):
        if cmd == "7z":
            return r"C:\Program Files-Zipz.exe"
        return None

    monkeypatch.setattr("utils.system_check.shutil.which", fake_which)

    assert checker._resolve_tool_path(r".z.exe") == ""
    assert checker.get_tool_command("7z") == [r"C:\Program Files-Zipz.exe"]
