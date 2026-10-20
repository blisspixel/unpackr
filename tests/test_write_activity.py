"""Point-in-time write checks. A quiet old file is settled; a changing file is held."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from unpackr.core.write_activity import WINDOW_SECONDS, Activity, drifted, file_stamp, observe, writer_visible


def _age(path: Path, seconds: float) -> None:
    stamp = path.stat().st_mtime - seconds
    os.utime(path, (stamp, stamp))


def test_old_unchanged_file_is_settled_without_extra_sleep(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"old")
    _age(video, 3600)
    slept: list[float] = []
    activity, result = observe(video, probe=lambda: "probed", sleep=slept.append, writers=lambda _path: False)
    assert result == "probed"
    assert activity.state == "settled"
    assert activity.reason == "mtime"
    assert slept == []


def test_growing_file_is_active(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"a")

    def probe() -> str:
        video.write_bytes(b"ab")
        return "grew"

    activity, result = observe(video, probe=probe, writers=lambda _path: False, sleep=lambda _seconds: None)
    assert result == "grew"
    assert activity.state == "active"
    assert activity.reason == "growing"
    assert activity.held


def test_recent_unchanged_file_waits_out_the_window(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fresh")
    slept: list[float] = []

    def clock() -> float:
        return video.stat().st_mtime + 0.2

    activity, _result = observe(
        video,
        writers=lambda _path: False,
        sleep=slept.append,
        clock=clock,
        monotonic=lambda: 0.0,
        window=WINDOW_SECONDS,
    )
    assert activity.state == "settled"
    assert activity.reason == "window"
    assert slept and abs(slept[0] - WINDOW_SECONDS) < 0.001


def test_visible_writer_holds_before_the_probe(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"open")
    called = {"probe": 0}

    def probe() -> None:
        called["probe"] += 1

    activity, _result = observe(video, probe=probe, writers=lambda _path: True, sleep=lambda _seconds: None)
    assert activity.state == "active"
    assert activity.reason == "writer"
    assert called["probe"] == 1


def test_unreadable_file_is_inconclusive(tmp_path: Path):
    missing = tmp_path / "gone.mkv"
    activity, result = observe(missing, probe=lambda: None, writers=lambda _path: False)
    assert result is None
    assert activity == Activity("inconclusive", "unreadable", None)
    assert activity.held


def test_drifted_catches_a_change_after_the_check(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"before")
    earlier = file_stamp(video)
    assert earlier is not None
    assert drifted(video, earlier, writers=lambda _path: False) is False
    video.write_bytes(b"after-more")
    assert drifted(video, earlier, writers=lambda _path: False) is True


def test_drifted_holds_when_the_stamp_was_never_read(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"x")
    assert drifted(video, None) is True


def test_writer_check_finishes_quickly_for_a_closed_file(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"closed")
    started = time.perf_counter()
    seen = writer_visible(video)
    assert time.perf_counter() - started < 2
    assert seen is not True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows reports an open handle as a sharing violation")
def test_open_handle_is_a_visible_writer(tmp_path: Path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"open")
    with video.open("rb"):
        assert writer_visible(video) is True
