import types

import vhealth


def _checker(tmp_path):
    class Cfg:
        video_extensions = [".mp4", ".mkv", ".avi"]

        def get(self, key, default=None):
            if key == "min_sample_size_mb":
                return 1
            return default

    return vhealth.VideoHealthChecker(Cfg())


def test_prescan_and_check_video_silent_branches(tmp_path, monkeypatch):
    checker = _checker(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * (2 * 1024 * 1024))

    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda _p: False,
        check_video_health=lambda _p, check_quality=True: (False, False, None, None),
    )
    assert "CORRUPT" in checker._check_video_silent(video)
    assert video in checker.corrupt_videos

    checker.corrupt_videos = []
    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda _p: False,
        check_video_health=lambda _p, check_quality=True: (True, True, "480p", (640, 480)),
    )
    out = checker._check_video_silent(video)
    assert "LOW QUALITY" in out
    assert checker.low_res_videos

    checker.low_res_videos = []
    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda _p: False,
        check_video_health=lambda _p, check_quality=True: (True, False, None, (1920, 1080)),
    )
    monkeypatch.setattr(checker, "_get_resolution", lambda _p: (640, 480))
    out = checker._check_video_silent(video, min_resolution="720p")
    assert "LOW RES" in out

    checker.low_res_videos = []
    checker.healthy_videos = []
    monkeypatch.setattr(checker, "_get_resolution", lambda _p: (1920, 1080))
    out = checker._check_video_silent(video, min_resolution="720p")
    assert out == "healthy"
    assert checker.healthy_videos == [video]


def test_check_video_and_prescan_with_sample_and_resolution(tmp_path, monkeypatch):
    checker = _checker(tmp_path)
    small = tmp_path / "small.mp4"
    small.write_bytes(b"x" * 100)
    large = tmp_path / "large.mp4"
    large.write_bytes(b"x" * (2 * 1024 * 1024))

    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda p: p == small,
        check_video_health=lambda _p, check_quality=True: (True, False, None, (1920, 1080)),
    )
    checker._prescan_videos([small, large], min_resolution="1080p", skip_samples=False)
    assert small in checker.sample_videos

    monkeypatch.setattr(checker, "_get_resolution", lambda _p: (640, 480))
    checker._check_video(large, min_resolution="720p", skip_health=True)
    assert checker.low_res_videos


def test_check_path_file_and_missing_path_branches(tmp_path, capsys, monkeypatch):
    checker = _checker(tmp_path)
    file_video = tmp_path / "f.mp4"
    file_video.write_bytes(b"x")

    seen = {"called": False}
    monkeypatch.setattr(checker, "_check_video", lambda *_args, **_kwargs: seen.__setitem__("called", True))
    checker.check_path(file_video)
    assert seen["called"] is True

    missing = tmp_path / "nope"
    checker.check_path(missing)
    out = capsys.readouterr().out
    assert "Path not found" in out


def test_find_videos_safe_size_and_delete_failures(tmp_path):
    checker = _checker(tmp_path)
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mkv"
    a.write_bytes(b"x" * 5)
    b.write_bytes(b"x" * 10)

    vids = checker._find_videos(tmp_path)
    assert vids[0] == b
    assert vids[1] == a

    # include missing path to hit delete failure branch
    checker._delete_videos([a, tmp_path / "missing.mp4"])


def test_find_videos_skips_linklike_paths(tmp_path, monkeypatch):
    checker = _checker(tmp_path)
    real = tmp_path / "real.mp4"
    nested = tmp_path / "nested"
    nested_video = nested / "nested.mp4"
    linked = tmp_path / "linked"
    real.write_bytes(b"x" * 5)
    nested.mkdir()
    nested_video.write_bytes(b"x" * 7)
    linked.mkdir()

    monkeypatch.setattr(checker, "_is_linklike_path", lambda path: path == linked)

    vids = checker._find_videos(tmp_path)
    assert vids == [nested_video, real]


def test_delete_videos_refuses_out_of_root_paths(tmp_path, monkeypatch):
    checker = _checker(tmp_path)
    inside = tmp_path / "inside.mp4"
    outside = tmp_path.parent / "outside.mp4"
    inside.write_bytes(b"x" * 5)
    outside.write_bytes(b"x" * 5)
    checker._active_root = tmp_path.resolve(strict=False)

    original_unsafe = checker._is_unsafe_path
    monkeypatch.setattr(checker, "_is_unsafe_path", lambda path, root: path == outside or original_unsafe(path, root))

    checker._delete_videos([inside, outside])

    assert inside.exists() is False
    assert outside.exists() is True
    outside.unlink(missing_ok=True)
