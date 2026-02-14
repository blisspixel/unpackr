import subprocess
import types

import pytest

from utils.safety import (
    LoopSafety,
    OperationTimer,
    RecursionSafety,
    StuckDetector,
    SubprocessSafety,
    TimeoutException,
    TimeoutGuard,
    timeout_decorator,
)


def test_timeout_guard_and_decorator_paths():
    with pytest.raises(TimeoutException):
        with TimeoutGuard(10, "tiny-op") as guard:
            guard._timeout_handler()

    @timeout_decorator(1, "decorated")
    def ok():
        return 123

    assert ok() == 123


def test_loop_recursion_timer_and_stuck_detector(monkeypatch):
    loop = LoopSafety(2, "L")
    assert loop.tick() is True
    assert loop.tick() is True
    assert loop.tick() is False
    loop.reset()
    assert loop.tick() is True

    rec = RecursionSafety(1, "R")
    assert rec.enter() is True
    assert rec.enter() is False
    rec.exit()
    assert rec.current_depth == 1
    rec.exit()
    assert rec.current_depth == 0

    fake_now = {"t": 100.0}
    monkeypatch.setattr("utils.safety.time.time", lambda: fake_now["t"])
    op = OperationTimer(10, "op")
    assert op.check() is True
    fake_now["t"] = 120.0
    assert op.check() is False
    assert op.elapsed() == 20.0

    sd = StuckDetector(timeout=10, check_interval=5)
    assert sd.check() is True  # not enough time passed for check
    fake_now["t"] = 140.0
    assert sd.check() is False  # stale progress
    sd.mark_progress()
    assert sd.check() is True


def test_subprocess_safety_pipe_modes(monkeypatch):
    class ProcOK:
        def __init__(self, *args, **kwargs):
            self.returncode = 0

        def communicate(self, timeout=None):
            return ("out", "err")

        def kill(self):
            pass

    monkeypatch.setattr("utils.safety.subprocess.Popen", ProcOK)
    tracker = types.SimpleNamespace(active_process=None)
    ok, out, err, code = SubprocessSafety.run_with_timeout(["echo"], timeout=1, process_tracker=tracker)
    assert ok is True
    assert code == 0
    assert tracker.active_process is None

    class ProcTimeout:
        def __init__(self, *args, **kwargs):
            self.returncode = 1
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(cmd=["x"], timeout=1)
            return ("partial", "killed")

        def kill(self):
            pass

    monkeypatch.setattr("utils.safety.subprocess.Popen", ProcTimeout)
    ok, out, err, code = SubprocessSafety.run_with_timeout(["x"], timeout=1)
    assert ok is False
    assert code == -1


def test_subprocess_safety_temp_file_modes(monkeypatch):
    class ProcTempOK:
        def __init__(self, cmd, stdout, stderr, cwd=None, text=None, encoding=None, errors=None):
            self.returncode = 0
            stdout.write("S")
            stderr.write("E")
            stdout.flush()
            stderr.flush()

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr("utils.safety.subprocess.Popen", ProcTempOK)
    ok, out, err, code = SubprocessSafety.run_with_timeout(["x"], timeout=1, use_temp_files=True)
    assert ok is True
    assert code == 0
    assert "S" in out
    assert "E" in err

    class ProcTempTimeout:
        def __init__(self, cmd, stdout, stderr, cwd=None, text=None, encoding=None, errors=None):
            self.returncode = 1

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd=["x"], timeout=1)

        def kill(self):
            pass

    monkeypatch.setattr("utils.safety.subprocess.Popen", ProcTempTimeout)
    ok, out, err, code = SubprocessSafety.run_with_timeout(["x"], timeout=1, use_temp_files=True)
    assert ok is False
    assert code == -1

    monkeypatch.setattr("utils.safety.subprocess.Popen", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    ok, out, err, code = SubprocessSafety.run_with_timeout(["x"], timeout=1)
    assert ok is False
    assert code == -1


def test_subprocess_safety_temp_tracker_warning_and_partial_read_fallback(monkeypatch):
    class ProcWarn:
        def __init__(self, cmd, stdout, stderr, cwd=None, text=None, encoding=None, errors=None):
            self.returncode = 2
            stdout.write("S")
            stderr.write("E")
            stdout.flush()
            stderr.flush()

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    tracker = types.SimpleNamespace(active_process=None)
    monkeypatch.setattr("utils.safety.subprocess.Popen", ProcWarn)
    ok, out, err, code = SubprocessSafety.run_with_timeout(
        ["x"], timeout=1, use_temp_files=True, expected_codes=[0], process_tracker=tracker
    )
    assert ok is False
    assert code == 2
    assert tracker.active_process is None

    class ProcTimeout:
        def __init__(self, cmd, stdout, stderr, cwd=None, text=None, encoding=None, errors=None):
            self.returncode = 1

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd=["x"], timeout=1)

        def kill(self):
            pass

    monkeypatch.setattr("utils.safety.subprocess.Popen", ProcTimeout)
    monkeypatch.setattr("pathlib.Path.read_text", lambda *a, **k: (_ for _ in ()).throw(OSError("io")))
    ok, out, err, code = SubprocessSafety.run_with_timeout(["x"], timeout=1, use_temp_files=True)
    assert ok is False
    assert code == -1
