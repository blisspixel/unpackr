import threading
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import psutil
import pytest

import unpackr
from core.config import Config
from core.file_handler import FileHandler
from utils.defensive import ValidationError


@pytest.fixture
def handler(tmp_path):
    stats = {"files_sanitized": 0}
    return FileHandler(Config(), stats=stats, destination_root=tmp_path / "dest")


def test_find_video_files_returns_empty_on_validation_error(handler):
    with patch("core.file_handler.InputValidator.validate_path", side_effect=ValidationError("bad path")):
        assert handler.find_video_files(Path("missing")) == []


def test_find_video_files_returns_empty_when_validator_returns_none(handler):
    with patch("core.file_handler.InputValidator.validate_path", return_value=None):
        assert handler.find_video_files(Path("missing")) == []


def test_find_video_files_rejects_invalid_video_extensions(handler, tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()
    (folder / "video.mp4").write_text("x", encoding="utf-8")
    handler.config = SimpleNamespace(video_extensions=None)

    assert handler.find_video_files(folder) == []


def test_find_video_files_returns_absolute_results_for_absolute_string_input(handler, tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()
    video = folder / "video.mp4"
    video.write_text("x", encoding="utf-8")

    results = handler.find_video_files(str(folder))
    assert results == [video]


def test_contains_non_video_files_skips_unreadable_child(handler, tmp_path):
    folder = Mock(spec=Path)
    unreadable = Mock()
    unreadable.is_file.side_effect = OSError("denied")
    unreadable.suffix = ".txt"
    readable = Mock()
    readable.is_file.return_value = False
    folder.rglob.return_value = [unreadable, readable]

    assert handler.contains_non_video_files(folder) is False


def test_contains_unwanted_files_skips_unreadable_child(handler, tmp_path):
    folder = Mock(spec=Path)
    unreadable = Mock()
    unreadable.is_file.side_effect = PermissionError("denied")
    unreadable.suffix = ".txt"
    readable = Mock()
    readable.is_file.return_value = False
    folder.rglob.return_value = [unreadable, readable]

    assert handler.contains_unwanted_files(folder) is False


def test_is_folder_empty_or_removable_rejects_uninspectable_child(handler):
    folder = Mock(spec=Path)
    folder.name = "root"
    bad_child = Mock(spec=Path)
    bad_child.is_dir.side_effect = OSError("denied")
    bad_child.name = "bad"
    folder.iterdir.return_value = [bad_child]
    with patch.object(handler, "_is_linklike_path", return_value=False):
        assert handler.is_folder_empty_or_removable(folder) is False


def test_is_folder_empty_or_removable_handles_incomplete_archives_and_empty_extension(handler, tmp_path):
    folder = tmp_path / "root"
    folder.mkdir()
    (folder / "archive.r1").write_text("x", encoding="utf-8")
    (folder / "archive.7z.001").write_text("x", encoding="utf-8")
    (folder / "abusefile").write_text("x", encoding="utf-8")

    assert handler.is_folder_empty_or_removable(folder) is True


def test_is_folder_empty_or_removable_misnamed_video_requires_archive_error(handler, tmp_path):
    folder = tmp_path / "root"
    folder.mkdir()
    misnamed = folder / "movie.mp4.1"
    misnamed.write_text("x", encoding="utf-8")

    assert handler.is_folder_empty_or_removable(folder, archive_error=False) is False
    assert handler.is_folder_empty_or_removable(folder, archive_error=True) is True


def test_safe_delete_folder_waits_on_generic_errors_then_falls_back(handler, tmp_path):
    target = tmp_path / "cleanup"
    target.mkdir()
    with (
        patch.object(handler, "is_folder_empty_or_removable", return_value=True),
        patch.object(handler, "_delete_tree_safely", side_effect=RuntimeError("boom")),
        patch.object(handler, "_tree_contains_linklike_entries", return_value=False),
        patch("core.file_handler.time.sleep") as mock_sleep,
        patch("subprocess.run", return_value=Mock()),
        patch("pathlib.Path.exists", lambda self: self != target),
    ):
        assert handler.safe_delete_folder(target, max_attempts=2) is True
    mock_sleep.assert_called_once()


def test_build_powershell_delete_command_uses_encoded_command(handler, tmp_path):
    folder = tmp_path / "odd'name"
    command = handler._build_powershell_delete_command(folder)
    assert command[:2] == ["powershell", "-NoProfile"]
    assert command[2] == "-EncodedCommand"
    assert command[3]


def test_is_linklike_path_returns_true_on_stat_errors(handler, tmp_path):
    path = tmp_path / "blocked"
    path.write_text("x", encoding="utf-8")
    with patch.object(Path, "is_symlink", side_effect=PermissionError("denied")):
        assert handler._is_linklike_path(path) is True


def test_tree_contains_linklike_entries_returns_true_for_walk_errors(handler):
    folder = Mock(spec=Path)
    folder.iterdir.side_effect = PermissionError("denied")
    with patch.object(handler, "_is_linklike_path", return_value=False):
        assert handler._tree_contains_linklike_entries(folder) is True


def test_delete_tree_safely_rejects_root_and_child_linklike_entries(handler, tmp_path):
    folder = tmp_path / "root"
    folder.mkdir()
    child = folder / "child"
    child.mkdir()
    with patch.object(handler, "_is_linklike_path", side_effect=lambda path: path == folder), pytest.raises(
        RuntimeError, match="Refusing to delete"
    ):
        handler._delete_tree_safely(folder)

    with patch.object(handler, "_is_linklike_path", side_effect=lambda path: path == child), pytest.raises(
        RuntimeError, match="Refusing to traverse"
    ):
        handler._delete_tree_safely(folder)


def test_kill_processes_using_folder_kills_once_and_waits(handler, tmp_path):
    folder = tmp_path / "root"
    folder.mkdir()
    proc = Mock()
    proc.pid = 42
    proc.name.return_value = "ffmpeg"
    proc.open_files.return_value = [SimpleNamespace(path=str(folder / "video.mp4"))]
    with (
        patch("core.file_handler.psutil.process_iter", return_value=[proc]),
        patch("core.file_handler.time.sleep") as mock_sleep,
    ):
        handler._kill_processes_using_folder(folder)

    proc.kill.assert_called_once()
    mock_sleep.assert_called_once_with(2)


def test_move_file_handles_none_validated_paths(handler, tmp_path):
    source = tmp_path / "video.mp4"
    dest = tmp_path / "dest"
    source.write_text("x", encoding="utf-8")
    dest.mkdir()
    with patch("core.file_handler.InputValidator.validate_path", side_effect=[None, dest]):
        assert handler.move_file(source, dest) is False


def test_move_file_fails_when_source_inaccessible(handler, tmp_path):
    source = tmp_path / "video.mp4"
    dest = tmp_path / "dest"
    source.write_text("x", encoding="utf-8")
    dest.mkdir()
    with patch("core.file_handler.StateValidator.check_file_accessible", return_value=False):
        assert handler.move_file(source, dest) is False


def test_move_file_fails_when_disk_space_insufficient(handler, tmp_path):
    source = tmp_path / "video.mp4"
    dest = tmp_path / "dest"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    dest.mkdir()
    with (
        patch("core.file_handler.StateValidator.check_file_accessible", return_value=True),
        patch("core.file_handler.StateValidator.check_dir_writable", return_value=True),
        patch("core.file_handler.StateValidator.check_disk_space", return_value=False),
        patch("shutil.disk_usage", return_value=SimpleNamespace(free=1 * 1024 * 1024)),
    ):
        assert handler.move_file(source, dest) is False


def test_move_file_continues_when_disk_space_check_raises(handler, tmp_path):
    source = tmp_path / "video.mp4"
    dest = tmp_path / "dest"
    source.write_text("x", encoding="utf-8")
    dest.mkdir()
    with (
        patch("core.file_handler.StateValidator.check_file_accessible", return_value=True),
        patch("core.file_handler.StateValidator.check_dir_writable", return_value=True),
        patch("core.file_handler.StateValidator.check_disk_space", side_effect=OSError("denied")),
        patch("core.file_handler.ErrorRecovery.safe_move", return_value=True),
    ):
        assert handler.move_file(source, dest) is True


def test_move_file_respects_enforcer(handler, tmp_path):
    source = tmp_path / "video.mp4"
    dest = tmp_path / "dest"
    source.write_text("x", encoding="utf-8")
    dest.mkdir()
    handler.enforcer = SimpleNamespace(enforce_move=Mock(side_effect=RuntimeError("blocked")))
    with (
        patch("core.file_handler.StateValidator.check_file_accessible", return_value=True),
        patch("core.file_handler.StateValidator.check_dir_writable", return_value=True),
        patch("core.file_handler.StateValidator.check_disk_space", return_value=True),
    ):
        assert handler.move_file(source, dest) is False


def test_delete_video_file_with_retry_respects_enforcer(handler, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("x", encoding="utf-8")
    handler.enforcer = SimpleNamespace(enforce_delete=Mock(side_effect=RuntimeError("blocked")))

    assert handler.delete_video_file_with_retry(video) is False


def test_delete_video_file_with_retry_logs_generic_exception(handler, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("x", encoding="utf-8")
    with patch.object(handler, "_terminate_related_processes"), patch.object(Path, "unlink", side_effect=RuntimeError("boom")):
        assert handler.delete_video_file_with_retry(video, max_attempts=1, retry_delay=1) is False


def test_wait_for_file_release_returns_true_after_access_denied_then_unlock(handler):
    denied_proc = Mock()
    denied_proc.open_files.side_effect = psutil.AccessDenied()
    free_proc = Mock()
    free_proc.open_files.return_value = []

    with patch("core.file_handler.psutil.process_iter", side_effect=[[denied_proc], [free_proc]]), patch(
        "core.file_handler.time.sleep"
    ):
        assert handler.wait_for_file_release("video.mp4", max_attempts=2, delay=1) is True


def test_terminate_related_processes_ignores_access_denied(handler):
    proc = Mock()
    proc.name.side_effect = psutil.AccessDenied()
    with patch("core.file_handler.psutil.process_iter", return_value=[proc]):
        handler._terminate_related_processes("video.mp4")


def test_load_comments_returns_empty_for_invalid_json(monkeypatch, tmp_path):
    config_dir = tmp_path / "config_files"
    config_dir.mkdir()
    comments = config_dir / "comments.json"
    comments.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(unpackr, "__file__", str(tmp_path / "unpackr.py"))

    assert unpackr.UnpackrApp._load_comments(SimpleNamespace()) == []


def test_load_comments_returns_rarity_format(monkeypatch, tmp_path):
    config_dir = tmp_path / "config_files"
    config_dir.mkdir()
    comments = config_dir / "comments.json"
    comments.write_text('{"comments":{"common":["hi"]},"rarities":{"common":{"weight":1}}}', encoding="utf-8")
    monkeypatch.setattr(unpackr, "__file__", str(tmp_path / "unpackr.py"))

    loaded = unpackr.UnpackrApp._load_comments(SimpleNamespace())
    assert isinstance(loaded, dict)
    assert "rarities" in loaded


def test_get_random_comment_returns_none_for_missing_pool_and_missing_comments(monkeypatch):
    dummy = SimpleNamespace(
        comments={"rarities": {}, "comments": {}},
        last_comment_folder=0,
        current_comment_display=None,
    )
    assert unpackr.UnpackrApp._get_random_comment(dummy, 10) is None

    dummy = SimpleNamespace(
        comments={"rarities": {"rare": {"weight": 1, "color": "red", "effect": "glow"}}, "comments": {}},
        last_comment_folder=0,
        current_comment_display=None,
    )
    monkeypatch.setattr(unpackr.random, "choice", lambda seq: seq[0])
    assert unpackr.UnpackrApp._get_random_comment(dummy, 10) is None


def test_remove_sample_videos_handles_dry_run_plan_fallback(tmp_path):
    sample = tmp_path / "movie.sample.mkv"
    full = tmp_path / "movie.1080p.mkv"
    sample.write_bytes(b"x" * (1 * 1024 * 1024))
    full.write_bytes(b"x" * (5 * 1024 * 1024))

    class Plan:
        def __init__(self):
            self.calls = 0

        def add_video_delete(self, *_args):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")

    app = SimpleNamespace(stats={"videos_sample": 0}, dry_run=True, dry_run_plan=Plan())
    result = unpackr.UnpackrApp._remove_sample_videos(app, [sample, full])
    assert result == [full]
    assert app.dry_run_plan.calls == 2


def test_stop_spinner_thread_handles_renderer_and_thread_join():
    renderer = Mock()
    app = SimpleNamespace(renderer=renderer, spinner_running=True, spinner_thread=None)
    unpackr.UnpackrApp._stop_spinner_thread(app)
    renderer.stop.assert_called_once()

    thread = Mock()
    app = SimpleNamespace(renderer=None, spinner_running=True, spinner_thread=thread)
    unpackr.UnpackrApp._stop_spinner_thread(app)
    assert app.spinner_running is False
    thread.join.assert_called_once_with(timeout=1.0)


def test_process_folder_skips_archive_extraction_after_par2_failure(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "set.par2").write_text("x", encoding="utf-8")
    (folder / "arc.rar").write_text("x", encoding="utf-8")
    destination = tmp_path / "dest"
    destination.mkdir()
    rar_calls = {"n": 0}
    remove_args = {}
    delete_args = {}

    app = SimpleNamespace(
        recursion_guard=SimpleNamespace(current_depth=5),
        _update_progress=lambda *_a, **_k: None,
        stuck_detector=SimpleNamespace(mark_progress=lambda: None),
        dry_run=False,
        dry_run_plan=None,
        archive_processor=SimpleNamespace(
            process_par2_files=lambda *_a, **_k: False,
            process_rar_files=lambda *_a, **_k: rar_calls.__setitem__("n", rar_calls["n"] + 1),
        ),
        file_handler=SimpleNamespace(
            find_video_files=lambda _folder: [],
            is_folder_empty_or_removable=lambda _folder, par2_error, archive_error: remove_args.update(
                {"par2_error": par2_error, "archive_error": archive_error}
            )
            or True,
            safe_delete_folder=lambda _folder, **kwargs: delete_args.update(kwargs) or True,
        ),
        _remove_sample_videos=lambda vids: vids,
        _process_subfolder=lambda *_a, **_k: None,
        stats={
            "videos_moved": 0,
            "folders_deleted": 0,
            "folders_processed": 0,
            "par2s_repaired": 0,
            "rars_extracted": 0,
            "videos_healthy": 0,
            "videos_corrupt": 0,
            "videos_failed": 0,
        },
        failed_deletions=[],
        video_processor=SimpleNamespace(check_video_health=lambda *_: True),
    )

    moved = unpackr.UnpackrApp.process_folder(app, folder, destination, 1, 1)
    assert moved == 0
    assert rar_calls["n"] == 0
    assert remove_args == {"par2_error": True, "archive_error": True}
    assert delete_args == {"par2_error": True, "archive_error": True}


def test_process_folder_handles_archive_stat_error_in_dry_run(tmp_path):
    folder = Mock(spec=Path)
    folder.name = "work"
    destination = tmp_path / "dest"
    destination.mkdir()
    recorded = []
    archive = Mock(spec=Path)
    archive.is_file.return_value = True
    archive.suffix = ".rar"
    archive.name = "arc.rar"
    archive.stat.side_effect = OSError("denied")
    subfolder = Mock(spec=Path)
    subfolder.is_file.return_value = False
    subfolder.is_dir.return_value = False
    folder.iterdir.side_effect = [[archive], [archive], [subfolder]]

    class Plan:
        def add_archive_extract(self, path, size):
            recorded.append((path, size))

    app = SimpleNamespace(
        recursion_guard=SimpleNamespace(current_depth=0),
        _update_progress=lambda *_a, **_k: None,
        stuck_detector=SimpleNamespace(mark_progress=lambda: None),
        dry_run=True,
        dry_run_plan=Plan(),
        archive_processor=SimpleNamespace(process_par2_files=lambda *_a, **_k: True, process_rar_files=lambda *_a, **_k: True),
        file_handler=SimpleNamespace(find_video_files=lambda _folder: [], is_folder_empty_or_removable=lambda *_a, **_k: False),
        _remove_sample_videos=lambda vids: vids,
        _process_subfolder=lambda *_a, **_k: None,
        stats={
            "videos_moved": 0,
            "folders_deleted": 0,
            "folders_processed": 0,
            "par2s_repaired": 0,
            "rars_extracted": 0,
            "videos_healthy": 0,
            "videos_corrupt": 0,
            "videos_failed": 0,
        },
        failed_deletions=[],
        video_processor=SimpleNamespace(check_video_health=lambda *_: True),
    )

    unpackr.UnpackrApp.process_folder(app, folder, destination, 1, 1)

    assert recorded == [(archive, 0)]


def test_process_folder_live_branches_for_failed_move_and_locked_corrupt_video(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    good = folder / "good.mp4"
    bad = folder / "bad.mp4"
    good.write_bytes(b"x" * 1024)
    bad.write_bytes(b"x" * 1024)
    destination = tmp_path / "dest"
    destination.mkdir()
    deleted = {"n": 0}

    app = SimpleNamespace(
        recursion_guard=SimpleNamespace(current_depth=0),
        _update_progress=lambda *_a, **_k: None,
        stuck_detector=SimpleNamespace(mark_progress=lambda: None),
        dry_run=False,
        dry_run_plan=None,
        archive_processor=SimpleNamespace(process_par2_files=lambda *_a, **_k: True, process_rar_files=lambda *_a, **_k: True),
        file_handler=SimpleNamespace(
            find_video_files=lambda _folder: [good, bad],
            move_file=lambda *_a, **_k: False,
            wait_for_file_release=lambda path: not path.endswith("bad.mp4"),
            delete_video_file_with_retry=lambda *_a, **_k: deleted.__setitem__("n", deleted["n"] + 1),
            is_folder_empty_or_removable=lambda *_a, **_k: False,
        ),
        _remove_sample_videos=lambda vids: vids,
        _process_subfolder=lambda *_a, **_k: None,
        stats={
            "videos_moved": 0,
            "folders_deleted": 0,
            "folders_processed": 0,
            "par2s_repaired": 0,
            "rars_extracted": 0,
            "videos_healthy": 0,
            "videos_corrupt": 0,
            "videos_failed": 0,
        },
        failed_deletions=[],
        video_processor=SimpleNamespace(check_video_health=lambda path: path.name == "good.mp4"),
    )

    moved = unpackr.UnpackrApp.process_folder(app, folder, destination, 1, 1)
    assert moved == 0
    assert app.stats["videos_healthy"] == 1
    assert app.stats["videos_corrupt"] == 1
    assert app.stats["videos_failed"] == 1
    assert deleted["n"] == 0


def test_update_progress_handles_renderer_plain_comment_and_eta_fallback(monkeypatch):
    calls = {"update": 0}

    class DummyRenderer:
        def start(self, _total):
            return None

        def update(self, **kwargs):
            calls["update"] += 1
            assert kwargs["comment_line"] == "plain comment"
            assert "calculating" in kwargs["time_line"]

        def stop(self):
            return None

    app = SimpleNamespace(
        spinner_lock=threading.Lock(),
        current_action="",
        spinner_frames=["-", "+"],
        spinner_index=0,
        start_time=1.0,
        stats={
            "videos_found": 1,
            "videos_moved": 0,
            "videos_corrupt": 0,
            "videos_sample": 0,
            "rars_extracted": 0,
            "par2s_repaired": 0,
            "folders_deleted": 0,
            "empty_folders_deleted": 0,
            "junk_files_deleted": 0,
            "safety_stops": 0,
        },
        first_progress_update=True,
        renderer=DummyRenderer(),
        _get_random_comment=lambda _cur: "plain comment",
    )
    monkeypatch.setattr(unpackr.time, "time", lambda: 5.0)
    unpackr.UnpackrApp._update_progress(app, current=1, total=10, action="Checking folder: demo")
    assert calls["update"] == 1


def test_retry_failed_deletions_handles_dry_run_and_missing_folders(tmp_path, monkeypatch):
    folder = tmp_path / "gone"
    app = SimpleNamespace(
        failed_deletions=deque([(folder, False, False)], maxlen=1000),
        dry_run=True,
        file_handler=SimpleNamespace(),
        stats={"folders_deleted": 0},
    )
    unpackr.UnpackrApp.retry_failed_deletions(app)
    assert len(app.failed_deletions) == 1

    folder.mkdir()
    app = SimpleNamespace(
        failed_deletions=deque([(folder, False, False)], maxlen=1000),
        dry_run=False,
        file_handler=SimpleNamespace(
            is_folder_empty_or_removable=lambda *_a, **_k: False,
            safe_delete_folder=lambda *_a, **_k: False,
        ),
        stats={"folders_deleted": 0},
    )
    monkeypatch.setattr(unpackr.time, "sleep", lambda *_: None)
    unpackr.UnpackrApp.retry_failed_deletions(app, max_passes=1, wait_seconds=0)
    assert len(app.failed_deletions) == 0


def test_cleanup_empty_folders_handles_progress_and_walk_errors(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    root.mkdir()
    child = root / "child"
    child.mkdir()

    app = SimpleNamespace(
        file_handler=SimpleNamespace(safe_delete_folder=lambda folder: folder.rmdir() is None or True),
        stats={"empty_folders_deleted": 0},
    )
    unpackr.UnpackrApp.cleanup_empty_folders(app, root, show_progress=True)
    assert app.stats["empty_folders_deleted"] == 1
    assert "Cleaned up 1 empty folders" in capsys.readouterr().out

    app = SimpleNamespace(
        file_handler=SimpleNamespace(safe_delete_folder=lambda folder: True),
        stats={"empty_folders_deleted": 0},
    )
    monkeypatch.setattr(unpackr.os, "walk", Mock(side_effect=RuntimeError("boom")))
    unpackr.UnpackrApp.cleanup_empty_folders(app, root, show_progress=False)
    assert app.stats["empty_folders_deleted"] == 0
