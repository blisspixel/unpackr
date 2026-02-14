import types

import vhealth


def _checker():
    class Cfg:
        video_extensions = [".mp4", ".mkv", ".avi"]

        def get(self, key, default=None):
            if key == "min_sample_size_mb":
                return 1
            return default

    return vhealth.VideoHealthChecker(Cfg())


def test_check_video_all_result_branches(tmp_path):
    checker = _checker()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * (2 * 1024 * 1024))

    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda _p: True,
        check_video_health=lambda *_a, **_k: (True, False, None, (1920, 1080)),
    )
    checker._check_video(video)
    assert checker.sample_videos == [video]

    checker.sample_videos = []
    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda _p: False,
        check_video_health=lambda *_a, **_k: (False, False, None, None),
    )
    checker._check_video(video)
    assert checker.corrupt_videos == [video]

    checker.corrupt_videos = []
    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda _p: False,
        check_video_health=lambda *_a, **_k: (True, True, "low bitrate", (640, 480)),
    )
    checker._check_video(video)
    assert checker.low_res_videos

    checker.low_res_videos = []
    checker.video_processor = types.SimpleNamespace(
        is_sample_file=lambda _p: False,
        check_video_health=lambda *_a, **_k: (True, False, None, (1920, 1080)),
    )
    checker._get_resolution = lambda _p: (640, 480)
    checker._check_video(video, min_resolution="720p", skip_health=False)
    assert checker.low_res_videos

    checker.low_res_videos = []
    checker._get_resolution = lambda _p: (1920, 1080)
    checker._check_video(video, min_resolution="720p", skip_health=False)
    assert checker.healthy_videos


def test_duration_and_resolution_error_branches(tmp_path, monkeypatch, capsys):
    checker = _checker()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")

    # Duration parse with malformed value -> handled and returns None.
    monkeypatch.setattr(
        vhealth.SubprocessSafety,
        "run_with_timeout",
        lambda *a, **k: (True, "", "Duration: bad,bits", 1),
    )
    assert checker._get_duration(video) is None

    # Duration outer exception
    monkeypatch.setattr(vhealth.SubprocessSafety, "run_with_timeout", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert checker._get_duration(video) is None

    # Resolution no match + exception branch.
    monkeypatch.setattr(vhealth.SubprocessSafety, "run_with_timeout", lambda *a, **k: (True, "nores", "", 1))
    assert checker._get_resolution(video) is None

    monkeypatch.setattr(vhealth.SubprocessSafety, "run_with_timeout", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert checker._get_resolution(video) is None

    # Unknown min resolution warning branch.
    assert checker._meets_min_resolution((1920, 1080), "mystery") is True
    out = capsys.readouterr().out
    assert "Unknown resolution" in out
