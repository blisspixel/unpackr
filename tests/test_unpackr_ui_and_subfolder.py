import threading
import types

import unpackr


def _base_stats():
    return {
        "videos_found": 10,
        "videos_moved": 3,
        "videos_corrupt": 1,
        "videos_sample": 1,
        "rars_extracted": 1,
        "par2s_repaired": 1,
        "folders_deleted": 1,
        "empty_folders_deleted": 1,
        "junk_files_deleted": 1,
        "safety_stops": 0,
    }


def test_update_progress_first_and_subsequent_render_paths(monkeypatch):
    app = types.SimpleNamespace(
        spinner_lock=threading.Lock(),
        current_action="",
        spinner_frames=["-", "+"],
        spinner_index=0,
        start_time=1.0,
        stats=_base_stats(),
        first_progress_update=True,
        _start_spinner_thread=lambda: None,
        _get_random_comment=lambda _cur: ("legend", "legendary", unpackr.Fore.YELLOW, "legendary"),
    )
    monkeypatch.setattr(unpackr.time, "time", lambda: 40.0)
    unpackr.UnpackrApp._update_progress(app, current=10, total=20, action="[x] Validate 1/2: file.mp4")

    # Second update should use cursor-move path and old-format fallback comment handling.
    app._get_random_comment = lambda _cur: "old-format comment"
    app.first_progress_update = False
    unpackr.UnpackrApp._update_progress(app, current=1, total=20, action="Scanning folder: test")


def test_update_progress_renderer_path(monkeypatch):
    calls = {"start": 0, "update": 0}

    class DummyRenderer:
        def start(self, _total):
            calls["start"] += 1

        def update(self, **kwargs):
            calls["update"] += 1
            assert kwargs["verb"] in {"extracting", "validating"}
            assert "speed:" in kwargs["time_line"]
            assert "\x1b[" not in kwargs["stats_line"]

        def stop(self):
            pass

    app = types.SimpleNamespace(
        spinner_lock=threading.Lock(),
        current_action="",
        spinner_frames=["-", "+"],
        spinner_index=0,
        start_time=1.0,
        stats=_base_stats(),
        first_progress_update=True,
        renderer=DummyRenderer(),
        _get_random_comment=lambda _cur: ("hello", "common", unpackr.Fore.YELLOW, "normal"),
    )
    monkeypatch.setattr(unpackr.time, "time", lambda: 40.0)
    unpackr.UnpackrApp._update_progress(app, current=10, total=20, action="[x] Extracting: arc.rar")
    app.first_progress_update = False
    unpackr.UnpackrApp._update_progress(app, current=11, total=20, action="[x] Validate 1/2: file.mp4")
    assert calls["start"] == 1
    assert calls["update"] == 2


def test_process_subfolder_dry_and_live_paths(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "set.par2").write_text("x", encoding="utf-8")
    (sub / "arc.rar").write_text("x", encoding="utf-8")
    v1 = sub / "ok.mp4"
    v2 = sub / "bad.mp4"
    v1.write_bytes(b"x")
    v2.write_bytes(b"x")
    destination = tmp_path / "dest"
    destination.mkdir()

    app_dry = types.SimpleNamespace(
        recursion_guard=types.SimpleNamespace(enter=lambda: True, exit=lambda: None),
        stats={"safety_stops": 0, "videos_found": 0, "videos_moved": 0, "par2s_repaired": 0, "rars_extracted": 0, "videos_healthy": 0, "videos_corrupt": 0, "videos_failed": 0},
        dry_run=True,
        archive_processor=types.SimpleNamespace(process_par2_files=lambda *_: True, process_rar_files=lambda *_: True),
        file_handler=types.SimpleNamespace(find_video_files=lambda _s: [v1], is_folder_empty_or_removable=lambda *_a, **_k: True),
        video_processor=types.SimpleNamespace(check_video_health=lambda *_: True),
        _process_subfolder=lambda *_a, **_k: None,
        failed_deletions=[],
    )
    unpackr.UnpackrApp._process_subfolder(app_dry, sub, destination)
    assert app_dry.stats["videos_found"] == 1
    assert app_dry.stats["videos_moved"] == 1

    deleted = {"n": 0}
    app_live = types.SimpleNamespace(
        recursion_guard=types.SimpleNamespace(enter=lambda: True, exit=lambda: None),
        stats={"safety_stops": 0, "videos_found": 0, "videos_moved": 0, "par2s_repaired": 0, "rars_extracted": 0, "videos_healthy": 0, "videos_corrupt": 0, "videos_failed": 0},
        dry_run=False,
        archive_processor=types.SimpleNamespace(process_par2_files=lambda *_: True, process_rar_files=lambda *_: True),
        file_handler=types.SimpleNamespace(
            find_video_files=lambda _s: [v1, v2],
            move_file=lambda *_a, **_k: True,
            wait_for_file_release=lambda *_a, **_k: True,
            delete_video_file_with_retry=lambda *_a, **_k: deleted.__setitem__("n", deleted["n"] + 1),
            is_folder_empty_or_removable=lambda *_a, **_k: True,
            safe_delete_folder=lambda *_a, **_k: False,
        ),
        video_processor=types.SimpleNamespace(check_video_health=lambda p: p.name == "ok.mp4"),
        _process_subfolder=lambda *_a, **_k: None,
        failed_deletions=[],
    )
    unpackr.UnpackrApp._process_subfolder(app_live, sub, destination)
    assert app_live.stats["videos_healthy"] == 1
    assert app_live.stats["videos_corrupt"] == 1
    assert deleted["n"] == 1
    assert app_live.failed_deletions
