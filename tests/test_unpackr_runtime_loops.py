from collections import deque
from pathlib import Path
import types

import unpackr


def test_run_handles_missing_or_empty_work_plan(capsys, tmp_path):
    app = types.SimpleNamespace(work_plan=None, destination_dir=None)
    unpackr.UnpackrApp.run(app, tmp_path, tmp_path)
    out = capsys.readouterr().out
    assert "No work plan available" in out

    app2 = types.SimpleNamespace(
        destination_dir=None,
        work_plan=types.SimpleNamespace(video_folders=[], content_folders=[], total_videos=0, loose_videos=[], junk_folders=[]),
    )
    unpackr.UnpackrApp.run(app2, tmp_path, tmp_path)
    out = capsys.readouterr().out
    assert "No video folders found" in out


def test_run_dry_run_loose_and_junk_paths(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    loose = tmp_path / "loose.mp4"
    loose.write_bytes(b"x")
    junk = tmp_path / "junk"
    junk.mkdir()

    app = types.SimpleNamespace(
        destination_dir=None,
        work_plan=types.SimpleNamespace(
            video_folders=[{"path": folder}],
            content_folders=[tmp_path / "keep"],
            total_videos=1,
            loose_videos=[loose],
            junk_folders=[junk],
        ),
        stats={
            "folders_preserved": 0,
            "videos_found": 0,
            "videos_moved": 0,
            "videos_healthy": 0,
            "videos_corrupt": 0,
            "videos_failed": 0,
            "folders_deleted": 0,
            "safety_stops": 0,
        },
        start_time=None,
        progress_current=0,
        current_comment_display=None,
        last_comment_folder=0,
        progress_total=0,
        config=types.SimpleNamespace(max_runtime_hours=1, max_videos_per_folder=10),
        stuck_detector=types.SimpleNamespace(check=lambda: True, mark_progress=lambda: None),
        process_folder=lambda *_a, **_k: 0,
        cancellation_requested=False,
        dry_run=True,
        dry_run_plan=types.SimpleNamespace(print_summary=lambda: None),
        video_processor=types.SimpleNamespace(check_video_health=lambda *_: True),
        file_handler=types.SimpleNamespace(is_folder_empty_or_removable=lambda *_a, **_k: True, safe_delete_folder=lambda *_a, **_k: True),
        _stop_spinner_thread=lambda: None,
    )

    unpackr.UnpackrApp.run(app, tmp_path, tmp_path / "dest")
    assert app.stats["folders_preserved"] == 1
    assert app.stats["videos_found"] == 1
    assert app.stats["videos_moved"] >= 1
    assert app.stats["folders_deleted"] >= 1


def test_retry_failed_deletions_and_cleanup_empty_folders(tmp_path, monkeypatch):
    removable = tmp_path / "removable"
    removable.mkdir()
    stuck = tmp_path / "stuck"
    stuck.mkdir()

    calls = {"safe": 0}

    def safe_delete(folder, **kwargs):
        calls["safe"] += 1
        return folder == removable

    app = types.SimpleNamespace(
        failed_deletions=deque([(removable, False, False), (stuck, False, False)], maxlen=1000),
        dry_run=False,
        file_handler=types.SimpleNamespace(
            is_folder_empty_or_removable=lambda folder, *_a, **_k: True,
            safe_delete_folder=safe_delete,
        ),
        stats={"folders_deleted": 0, "empty_folders_deleted": 0},
    )

    monkeypatch.setattr(unpackr.time, "sleep", lambda *_: None)
    unpackr.UnpackrApp.retry_failed_deletions(app, max_passes=2, wait_seconds=0)
    assert app.stats["folders_deleted"] >= 1

    root = tmp_path / "cleanup"
    root.mkdir()
    empty_child = root / "empty"
    empty_child.mkdir()
    non_empty = root / "nonempty"
    non_empty.mkdir()
    (non_empty / "x.txt").write_text("x", encoding="utf-8")

    app2 = types.SimpleNamespace(
        file_handler=types.SimpleNamespace(safe_delete_folder=lambda folder: folder.rmdir() is None or True),
        stats={"empty_folders_deleted": 0},
    )
    unpackr.UnpackrApp.cleanup_empty_folders(app2, root, show_progress=False)
    assert app2.stats["empty_folders_deleted"] >= 1


def test_display_summary_prints_tip(capsys):
    app = types.SimpleNamespace(
        start_time=0,
        cancellation_requested=False,
        stats={
            "folders_processed": 1,
            "folders_deleted": 1,
            "empty_folders_deleted": 1,
            "folders_preserved": 1,
            "videos_found": 1,
            "videos_moved": 1,
            "videos_sample": 0,
            "videos_corrupt": 0,
            "videos_failed": 0,
            "rars_extracted": 0,
            "par2s_repaired": 0,
            "files_sanitized": 0,
            "safety_stops": 0,
        },
        failed_deletions=[],
        destination_dir=Path("D:/Videos"),
    )
    unpackr.UnpackrApp.display_summary(app)
    out = capsys.readouterr().out
    assert "Tip: Run 'vhealth" in out
