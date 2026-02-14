"""Extra coverage tests for vhealth helpers and interaction branches."""

from pathlib import Path

import vhealth


def test_get_duration_parses_ffmpeg_output(monkeypatch, tmp_path):
    checker = vhealth.VideoHealthChecker(vhealth.Config())
    video = tmp_path / "video.mkv"
    video.write_bytes(b"x")

    stderr = "Duration: 00:01:30.50, start: 0.000000, bitrate: 1200 kb/s"
    monkeypatch.setattr(
        vhealth.SubprocessSafety,
        "run_with_timeout",
        staticmethod(lambda *args, **kwargs: (True, "", stderr, 1)),
    )

    duration = checker._get_duration(video)
    assert duration == 90.5


def test_get_resolution_parses_dimensions(monkeypatch, tmp_path):
    checker = vhealth.VideoHealthChecker(vhealth.Config())
    video = tmp_path / "video.mkv"
    video.write_bytes(b"x")

    out = "Stream #0:0: Video: h264, yuv420p, 1920x1080"
    monkeypatch.setattr(
        vhealth.SubprocessSafety,
        "run_with_timeout",
        staticmethod(lambda *args, **kwargs: (True, out, "", 1)),
    )

    resolution = checker._get_resolution(video)
    assert resolution == (1920, 1080)


def test_prompt_delete_branches(monkeypatch, tmp_path):
    checker = vhealth.VideoHealthChecker(vhealth.Config())
    video = tmp_path / "bad.mkv"
    video.write_bytes(b"x")

    calls = {"count": 0}

    def fake_delete(videos):
        calls["count"] += len(videos)

    checker._delete_videos = fake_delete

    monkeypatch.setattr("builtins.input", lambda *_: "y")
    checker._prompt_delete([video])
    assert calls["count"] == 1

    monkeypatch.setattr("builtins.input", lambda *_: "n")
    checker._prompt_delete([video])
    assert calls["count"] == 1


def test_print_summary_all_healthy(capsys):
    checker = vhealth.VideoHealthChecker(vhealth.Config())
    checker.healthy_videos = [Path("a.mkv")]
    checker.print_summary(auto_delete=False)
    out = capsys.readouterr().out
    assert "All videos healthy" in out

