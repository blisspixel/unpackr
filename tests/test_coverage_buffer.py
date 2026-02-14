from core import logger as core_logger
from utils.system_check import SystemCheck


def test_logger_cleanup_warning_and_subprocess_no_output(monkeypatch, tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    for idx in range(3):
        (logs_dir / f"unpackr-20200101-00000{idx}.log").write_text("x", encoding="utf-8")

    monkeypatch.setattr(core_logger.os, "remove", lambda *_: (_ for _ in ()).throw(OSError("locked")))
    core_logger.cleanup_old_logs(logs_dir, max_files=1)

    seen = []
    monkeypatch.setattr(core_logger.logging, "error", lambda msg: seen.append(msg))

    class FakeErr:
        returncode = 1
        cmd = ["tool", "--x"]
        output = ""

    core_logger.log_subprocess_error(FakeErr(), "tool")
    assert any("return code 1" in str(m) for m in seen)
    assert all("Output:" not in str(m) for m in seen)


def test_system_check_warn_running_processes_keyboard_interrupt(monkeypatch):
    checker = SystemCheck()
    monkeypatch.setattr(checker, "check_running_processes", lambda: (True, ["7-Zip"]))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(checker, "kill_processes", lambda *_: True)

    # Force leftovers so input() branch executes, then Ctrl+C path returns False.
    seq = iter([(True, ["7-Zip"]), (True, ["7-Zip"])])
    monkeypatch.setattr(checker, "check_running_processes", lambda: next(seq))
    assert checker.warn_running_processes() is False
