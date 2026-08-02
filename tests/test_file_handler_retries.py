import base64
import tempfile
from pathlib import Path

from core.config import Config
from core.file_handler import FileHandler


def _handler():
    return FileHandler(Config())


def test_safe_delete_folder_aborts_when_not_removable(monkeypatch, tmp_path):
    handler = _handler()
    folder = tmp_path / "keep"
    folder.mkdir()

    monkeypatch.setattr(handler, "is_folder_empty_or_removable", lambda *args, **kwargs: False)

    assert handler.safe_delete_folder(folder, max_attempts=1) is False
    assert folder.exists()


def test_safe_delete_folder_success_first_try(tmp_path):
    handler = _handler()
    folder = tmp_path / "junk"
    folder.mkdir()
    (folder / "info.nfo").write_text("x", encoding="utf-8")

    assert handler.safe_delete_folder(folder, max_attempts=1) is True
    assert not folder.exists()


def test_safe_delete_folder_powershell_fallback_encodes_literal_path(tmp_path, monkeypatch):
    handler = _handler()
    folder = tmp_path / "bad;name'&calc"
    folder.mkdir()

    captured = {}

    def fake_rmtree(_folder):
        raise OSError("locked")

    def fake_force_delete(target):
        captured["command"] = handler._build_powershell_delete_command(target)
        return True

    monkeypatch.setattr(handler, "is_folder_empty_or_removable", lambda *args, **kwargs: True)
    monkeypatch.setattr(handler, "_delete_tree_safely", fake_rmtree)
    monkeypatch.setattr(handler, "_tree_contains_linklike_entries", lambda path: False)
    monkeypatch.setattr("core.file_handler.force_delete_directory", fake_force_delete)
    monkeypatch.setattr("core.file_handler.is_windows", lambda: True)

    assert handler.safe_delete_folder(folder, max_attempts=1) is True

    args = captured["command"]
    assert args[:3] == ["powershell", "-NoProfile", "-EncodedCommand"]
    assert str(folder) not in args

    decoded = base64.b64decode(args[3]).decode("utf-16le")
    assert "Remove-Item -LiteralPath $target" in decoded
    escaped_folder = str(folder).replace("'", "''")
    assert f"$target = '{escaped_folder}'" in decoded


def test_safe_delete_folder_aborts_when_delete_tree_finds_linklike_entry(tmp_path, monkeypatch):
    handler = _handler()
    folder = tmp_path / "junk"
    child = folder / "nested"
    folder.mkdir()
    child.mkdir()
    (child / "info.nfo").write_text("x", encoding="utf-8")

    monkeypatch.setattr(handler, "is_folder_empty_or_removable", lambda *args, **kwargs: True)
    monkeypatch.setattr(handler, "_is_linklike_path", lambda path: path == child)

    assert handler.safe_delete_folder(folder, max_attempts=1) is False
    assert folder.exists()


def test_delete_video_file_with_retry_success(tmp_path, monkeypatch):
    handler = _handler()
    video = tmp_path / "video.mkv"
    video.write_text("x", encoding="utf-8")

    monkeypatch.setattr(handler, "_terminate_related_processes", lambda *_: None)
    assert handler.delete_video_file_with_retry(video, max_attempts=1, retry_delay=0) is True
    assert not video.exists()


def test_delete_video_file_with_retry_failure_logs_error(tmp_path, monkeypatch):
    handler = _handler()
    video = tmp_path / "video.mkv"
    video.write_text("x", encoding="utf-8")

    monkeypatch.setattr(handler, "_terminate_related_processes", lambda *_: None)
    monkeypatch.setattr(
        "core.file_handler.Path.unlink", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError())
    )
    monkeypatch.setattr("core.file_handler.time.sleep", lambda *_: None)

    assert handler.delete_video_file_with_retry(video, max_attempts=2, retry_delay=0) is False


def test_wait_for_file_release_unlocks_after_retry(monkeypatch):
    handler = _handler()

    class FakeProc:
        def __init__(self, locked):
            self._locked = locked

        def open_files(self):
            if self._locked:
                return [type("F", (), {"path": "C:/video.mkv"})()]
            return []

    state = {"calls": 0}

    def fake_iter(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            return [FakeProc(True)]
        return [FakeProc(False)]

    monkeypatch.setattr("core.file_handler.psutil.process_iter", fake_iter)
    monkeypatch.setattr("core.file_handler.time.sleep", lambda *_: None)
    assert handler.wait_for_file_release("C:/video.mkv", max_attempts=3, delay=0) is True


def test_terminate_related_processes_kills_matching_process(monkeypatch):
    handler = _handler()

    class FakeProc:
        def __init__(self, name, cmdline):
            self._name = name
            self._cmdline = cmdline
            self.terminated = False

        @property
        def pid(self):
            return 1

        def name(self):
            return self._name

        def cmdline(self):
            return self._cmdline

        def terminate(self):
            self.terminated = True

    p1 = FakeProc("ffmpeg", ["ffmpeg", "C:/video.mkv"])
    p2 = FakeProc("other", ["other", "x"])
    monkeypatch.setattr("core.file_handler.psutil.process_iter", lambda *args, **kwargs: [p1, p2])
    handler._terminate_related_processes("C:/video.mkv")
    assert p1.terminated is True
    assert p2.terminated is False


def test_kill_processes_using_folder_handles_errors(monkeypatch):
    handler = _handler()

    class FakeProc:
        pid = 123

        def name(self):
            return "worker"

        def open_files(self):
            raise PermissionError("denied")

        def kill(self):
            raise RuntimeError("should not be called")

    monkeypatch.setattr("core.file_handler.psutil.process_iter", lambda *_: [FakeProc()])
    handler._kill_processes_using_folder(Path(tempfile.gettempdir()))
