"""Regression tests for robust video discovery in vhealth."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unpackr.core import Config
from unpackr.vhealth import VideoHealthChecker


def test_find_videos_handles_unreadable_paths(monkeypatch, tmp_path):
    """Discovery should continue when one directory walk hits OSError."""
    config = Config()
    config.set("video_extensions", [".mkv", ".mp4"])
    checker = VideoHealthChecker(config)

    readable_video = tmp_path / "ok.mp4"
    blocked_dir = tmp_path / "blocked"
    readable_video.write_bytes(b"video")
    blocked_dir.mkdir()

    original_iter = checker._iter_directory_entries

    def fake_iter(directory):
        if directory == blocked_dir:
            raise OSError("locked volume")
        return original_iter(directory)

    monkeypatch.setattr(checker, "_iter_directory_entries", fake_iter)
    videos = checker._find_videos(tmp_path)
    assert videos == [readable_video]


def test_find_videos_sorts_by_size_desc(tmp_path):
    """Discovery returns largest files first."""
    config = Config()
    config.set("video_extensions", [".mp4"])
    checker = VideoHealthChecker(config)

    large = tmp_path / "large.mp4"
    small = tmp_path / "small.mp4"
    large.write_bytes(b"a" * 32)
    small.write_bytes(b"a" * 8)

    videos = checker._find_videos(tmp_path)
    assert videos == [large, small]
