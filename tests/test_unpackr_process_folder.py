import types

import unpackr


class _DryRunPlan:
    def __init__(self):
        self.calls = []

    def add_par2_process(self, folder, count):
        self.calls.append(("par2", folder, count))

    def add_archive_extract(self, archive, size):
        self.calls.append(("archive", archive, size))

    def add_video_move(self, video, size, resolution):
        self.calls.append(("video", video, size, resolution))

    def add_folder_delete(self, folder):
        self.calls.append(("delete_folder", folder))


def test_process_folder_dry_run_full_path(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "set.par2").write_text("x", encoding="utf-8")
    (folder / "arc.rar").write_text("x", encoding="utf-8")
    video = folder / "movie.mp4"
    video.write_bytes(b"x" * 1024)
    sub = folder / "sub"
    sub.mkdir()
    destination = tmp_path / "dest"
    destination.mkdir()

    app = types.SimpleNamespace(
        recursion_guard=types.SimpleNamespace(current_depth=99),
        _update_progress=lambda *_args, **_kwargs: None,
        stuck_detector=types.SimpleNamespace(mark_progress=lambda: None),
        dry_run=True,
        dry_run_plan=_DryRunPlan(),
        archive_processor=types.SimpleNamespace(
            process_par2_files=lambda *_a, **_k: True,
            process_rar_files=lambda *_a, **_k: True,
        ),
        file_handler=types.SimpleNamespace(
            find_video_files=lambda _folder: [video],
            is_folder_empty_or_removable=lambda *_a, **_k: True,
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
        video_processor=types.SimpleNamespace(check_video_health=lambda *_: True),
    )

    moved = unpackr.UnpackrApp.process_folder(app, folder, destination, 1, 1)
    assert moved == 1
    assert app.stats["videos_moved"] == 1
    assert app.stats["folders_deleted"] == 1
    assert app.stats["folders_processed"] == 1
    assert any(c[0] == "par2" for c in app.dry_run_plan.calls)
    assert any(c[0] == "archive" for c in app.dry_run_plan.calls)
    assert any(c[0] == "video" for c in app.dry_run_plan.calls)


def test_process_folder_live_path_with_corrupt_and_failed_delete(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    good = folder / "good.mp4"
    bad = folder / "bad.mp4"
    good.write_bytes(b"x" * 1024)
    bad.write_bytes(b"x" * 1024)
    destination = tmp_path / "dest"
    destination.mkdir()

    deleted = {"count": 0}

    def check_video(v):
        return v.name == "good.mp4"

    app = types.SimpleNamespace(
        recursion_guard=types.SimpleNamespace(current_depth=99),
        _update_progress=lambda *_args, **_kwargs: None,
        stuck_detector=types.SimpleNamespace(mark_progress=lambda: None),
        dry_run=False,
        dry_run_plan=None,
        archive_processor=types.SimpleNamespace(
            process_par2_files=lambda *_a, **_k: True,
            process_rar_files=lambda *_a, **_k: True,
        ),
        file_handler=types.SimpleNamespace(
            find_video_files=lambda _folder: [good, bad],
            move_file=lambda *_a, **_k: True,
            wait_for_file_release=lambda *_a, **_k: True,
            delete_video_file_with_retry=lambda *_a, **_k: deleted.__setitem__("count", deleted["count"] + 1),
            is_folder_empty_or_removable=lambda *_a, **_k: True,
            safe_delete_folder=lambda *_a, **_k: False,
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
        video_processor=types.SimpleNamespace(check_video_health=check_video),
    )

    moved = unpackr.UnpackrApp.process_folder(app, folder, destination, 1, 1)
    assert moved == 1
    assert app.stats["videos_healthy"] == 1
    assert app.stats["videos_corrupt"] == 1
    assert app.stats["videos_failed"] == 1
    assert deleted["count"] == 1
    assert app.failed_deletions
