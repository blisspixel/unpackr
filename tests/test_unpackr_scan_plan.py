import threading
import time
import types

import unpackr


class DummyConfig:
    video_extensions = [".mp4", ".mkv", ".avi", ".mov"]
    music_extensions = [".mp3"]
    image_extensions = [".jpg"]
    document_extensions = [".pdf"]
    min_music_files = 1
    min_image_files = 1
    min_documents = 1


def test_threadsafe_stats_and_workplan_display(capsys, tmp_path):
    stats = unpackr.ThreadSafeStats()
    stats.increment("videos_found", 2)
    assert stats["videos_found"] == 2
    snap = stats.get_snapshot()
    assert snap["videos_found"] == 2

    plan = unpackr.WorkPlan()
    plan.add_video_folder(tmp_path, videos=2, rars=1, par2s=1)
    plan.add_content_folder(tmp_path / "content", "music")
    plan.add_junk_folder(tmp_path / "junk")
    plan.add_loose_video(tmp_path / "loose.mp4")
    assert plan.calculate_time_estimate() > 0
    plan.display()
    plan.display_detailed()
    out = capsys.readouterr().out
    assert "SUMMARY:" in out


def test_scan_and_plan_classifies_and_renames(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    # Root file ensures root scan path is included.
    (source / "movie.mp4.1").write_bytes(b"x")
    (source / "loose.mp4").write_bytes(b"x")

    video_folder = source / "video_folder"
    video_folder.mkdir()
    (video_folder / "arch.rar").write_text("x", encoding="utf-8")
    (video_folder / "set.par2").write_text("x", encoding="utf-8")

    content_folder = source / "content_folder"
    content_folder.mkdir()
    (content_folder / "a.mp3").write_text("x", encoding="utf-8")
    (content_folder / "b.mp3").write_text("x", encoding="utf-8")

    junk_folder = source / "junk_folder"
    junk_folder.mkdir()
    (junk_folder / "note.txt").write_text("x", encoding="utf-8")

    dummy = types.SimpleNamespace(config=DummyConfig(), work_plan=None)
    plan = unpackr.UnpackrApp.scan_and_plan(dummy, source)

    assert (source / "movie.mp4").exists()
    assert any("video_folder" in str(v["path"]) for v in plan.video_folders)
    assert any("content_folder" in str(v["path"]) for v in plan.content_folders)
    assert any("junk_folder" in str(v) for v in plan.junk_folders)
    assert any(v.name == "loose.mp4" for v in plan.loose_videos)


def test_spinner_start_stop_and_comment_rarity_paths(monkeypatch):
    app = types.SimpleNamespace(
        spinner_running=False,
        spinner_thread=None,
        _spinner_loop=lambda: time.sleep(0.01),
        comments={
            "rarities": {"common": {"weight": 1, "color": "green", "effect": "normal"}},
            "comments": {"common": ["hello"]},
        },
        last_comment_folder=-10,
        current_comment_display=None,
    )

    unpackr.UnpackrApp._start_spinner_thread(app)
    assert app.spinner_running is True
    assert isinstance(app.spinner_thread, threading.Thread)
    unpackr.UnpackrApp._stop_spinner_thread(app)
    assert app.spinner_running is False

    monkeypatch.setattr(unpackr.random, "choice", lambda seq: seq[0])
    result = unpackr.UnpackrApp._get_random_comment(app, 10)
    assert result is not None
    assert result[0] == "hello"


def test_scan_and_plan_skips_unreadable_subfolder(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "root.mp4").write_bytes(b"x")
    good = source / "good"
    good.mkdir()
    (good / "movie.mp4").write_bytes(b"x")
    blocked = source / "blocked"
    blocked.mkdir()

    original_iterdir = unpackr.Path.iterdir

    def patched_iterdir(path_obj):
        if path_obj == blocked:
            raise PermissionError("denied")
        return original_iterdir(path_obj)

    monkeypatch.setattr(unpackr.Path, "iterdir", patched_iterdir)
    dummy = types.SimpleNamespace(config=DummyConfig(), work_plan=None)
    plan = unpackr.UnpackrApp.scan_and_plan(dummy, source)
    assert any("good" in str(v["path"]) for v in plan.video_folders)


def test_scan_and_plan_handles_unreadable_source(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    original_iterdir = unpackr.Path.iterdir

    def patched_iterdir(path_obj):
        if path_obj == source:
            raise PermissionError("denied")
        return original_iterdir(path_obj)

    monkeypatch.setattr(unpackr.Path, "iterdir", patched_iterdir)
    dummy = types.SimpleNamespace(config=DummyConfig(), work_plan=None)
    plan = unpackr.UnpackrApp.scan_and_plan(dummy, source)
    assert plan.total_videos == 0
    assert len(plan.video_folders) == 0


def test_scan_and_plan_handles_unreadable_stat_in_sort(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    good = source / "good"
    good.mkdir()
    blocked = source / "blocked"
    blocked.mkdir()
    (good / "movie.mp4").write_bytes(b"x")

    original_stat = unpackr.Path.stat

    def patched_stat(path_obj):
        if path_obj == blocked:
            raise PermissionError("denied")
        return original_stat(path_obj)

    monkeypatch.setattr(unpackr.Path, "stat", patched_stat)
    dummy = types.SimpleNamespace(config=DummyConfig(), work_plan=None)
    plan = unpackr.UnpackrApp.scan_and_plan(dummy, source)
    assert any("good" in str(v["path"]) for v in plan.video_folders)


def test_scan_and_plan_handles_unreadable_file_check(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    inaccessible = source / "weird.bin"
    inaccessible.write_bytes(b"x")
    (source / "movie.mp4").write_bytes(b"x")

    original_is_file = unpackr.Path.is_file

    def patched_is_file(path_obj):
        if path_obj == inaccessible:
            raise PermissionError("denied")
        return original_is_file(path_obj)

    monkeypatch.setattr(unpackr.Path, "is_file", patched_is_file)
    dummy = types.SimpleNamespace(config=DummyConfig(), work_plan=None)
    plan = unpackr.UnpackrApp.scan_and_plan(dummy, source)
    assert any(v.name == "movie.mp4" for v in plan.loose_videos)
