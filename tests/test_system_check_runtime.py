import types

from utils.system_check import SystemCheck


def test_check_running_processes_windows_and_linux(monkeypatch):
    checker = SystemCheck()

    monkeypatch.setattr("utils.system_check.sys.platform", "win32")
    monkeypatch.setattr(
        "utils.system_check.subprocess.run",
        lambda *a, **k: types.SimpleNamespace(stdout="7z.exe\npar2.exe\n"),
    )
    has_conflicts, running = checker.check_running_processes()
    assert has_conflicts is True
    assert "7-Zip" in running
    assert "par2" in running

    monkeypatch.setattr("utils.system_check.sys.platform", "linux")
    monkeypatch.setattr(
        "utils.system_check.subprocess.run",
        lambda *a, **k: types.SimpleNamespace(stdout="7z process\npar2 process\n"),
    )
    has_conflicts, running = checker.check_running_processes()
    assert has_conflicts is True
    assert "7-Zip" in running
    assert "par2" in running


def test_warn_running_processes_auto_kill_paths(monkeypatch):
    checker = SystemCheck()
    monkeypatch.setattr(checker, "kill_processes", lambda process_names: True)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    # second status check: no leftovers
    states = iter([(True, ["7-Zip"]), (False, [])])
    monkeypatch.setattr(checker, "check_running_processes", lambda: next(states))
    assert checker.warn_running_processes() is True

    # Leftovers branch with continue prompt
    checker2 = SystemCheck()
    states2 = iter([(True, ["7-Zip"]), (True, ["7-Zip"])])
    monkeypatch.setattr(checker2, "check_running_processes", lambda: next(states2))
    monkeypatch.setattr(checker2, "kill_processes", lambda process_names: False)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    assert checker2.warn_running_processes() is True
