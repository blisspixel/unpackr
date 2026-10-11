"""Regression tests for video verdicts and archive-set handling.

Covers issue #2 (short videos are previews, reported as such, and the dry run
says so), issue #3 (incomplete archive sets are kept and reported, never called
path traversal) and issue #4 (truncated videos are rejected).
"""

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import unpackr
from conftest import bind_app_helpers
from core.archive_processor import (
    ArchiveProcessor,
    classify_extract_failure,
    find_archive_sets,
)
from core.config import Config
from core.file_handler import FileHandler
from core.video_processor import (
    VideoProcessor,
    parse_ffmpeg_duration,
    parse_progress_seconds,
)

REPO = Path(__file__).resolve().parent.parent


def _meta(duration: str) -> str:
    return (
        f"Input #0, matroska,webm, from 'x.mkv':\n  Duration: {duration}, start: 0.000000, bitrate: 2000 kb/s\n"
        "  Stream #0:0: Video: h264, yuv420p, 640x360, 30 fps\n"
    )


def _video(tmp_path: Path, name: str = "v.mkv", size_mb: int = 2) -> Path:
    path = tmp_path / name
    path.write_bytes(b"\0" * (size_mb * 1024 * 1024))
    return path


def _processor(**config) -> VideoProcessor:
    vp = VideoProcessor(config or {})
    vp.system_check.get_tool_command = Mock(return_value=["ffmpeg"])
    return vp


# ---------------------------------------------------------------------------
# Video verdicts
# ---------------------------------------------------------------------------


class TestVideoVerdicts:
    def test_parsers(self):
        assert parse_ffmpeg_duration(_meta("00:01:02.50")) == pytest.approx(62.5)
        assert parse_ffmpeg_duration("no duration here") is None
        assert parse_progress_seconds("frame=1\nout_time_us=7500000\nprogress=end\n") == pytest.approx(7.5)
        assert parse_progress_seconds("out_time_us=N/A\n") is None

    def test_short_video_is_a_preview_not_corrupt(self, tmp_path):
        vp = _processor()
        with patch(
            "core.video_processor.SubprocessSafety.run_with_timeout",
            return_value=(True, "", _meta("00:00:08.02"), 1),
        ) as run:
            assert vp.check_video_health(_video(tmp_path)) is False
        assert run.call_count == 1  # no stream read for a preview
        assert vp.last_verdict.category == "preview"
        assert vp.last_verdict.reason_code == "video_too_short"
        assert "8.0s" in vp.last_verdict.detail

    def test_minimum_duration_is_configurable_and_can_be_disabled(self, tmp_path):
        meta = (True, "", _meta("00:00:08.02"), 1)
        stream = (True, "out_time_us=8020000\nprogress=end\n", "", 0)
        vp = _processor(min_video_duration_seconds=0)
        with patch("core.video_processor.SubprocessSafety.run_with_timeout", side_effect=[meta, stream]):
            assert vp.check_video_health(_video(tmp_path)) is True
        vp = _processor(min_video_duration_seconds=5)
        with patch("core.video_processor.SubprocessSafety.run_with_timeout", side_effect=[meta, stream]):
            assert vp.check_video_health(_video(tmp_path)) is True

    def test_config_object_threshold_is_used(self):
        cfg = Config()
        cfg.set("min_video_duration_seconds", 30)
        vp = VideoProcessor(cfg)
        assert vp.min_duration_seconds == 30
        assert vp.classify_preview(25.0).reason_code == "video_too_short"
        assert vp.classify_preview(31.0) is None
        assert vp.classify_preview(None) is None

    def test_missing_duration_is_corrupt(self, tmp_path):
        vp = _processor()
        with patch("core.video_processor.SubprocessSafety.run_with_timeout", return_value=(True, "", "garbage", 1)):
            assert vp.check_video_health(_video(tmp_path)) is False
        assert vp.last_verdict.category == "corrupt"
        assert vp.last_verdict.reason_code == "video_duration_missing"

    @pytest.mark.parametrize(
        "stderr,category",
        [
            ("[in#0/matroska,webm @ 0x1] File ended prematurely", "truncated"),
            ("[in#0/mov,mp4 @ 0x1] stream 0, offset 0x1c8dd7: partial file", "truncated"),
            ("Invalid data found when processing input", "corrupt"),
        ],
    )
    def test_ffmpeg_messages_reject_damaged_files(self, tmp_path, stderr, category):
        vp = _processor()
        side = [(True, "", _meta("00:00:15.00"), 1), (True, "out_time_us=15000000\n", stderr, 0)]
        with patch("core.video_processor.SubprocessSafety.run_with_timeout", side_effect=side):
            assert vp.check_video_health(_video(tmp_path)) is False
        assert vp.last_verdict.category == category

    def test_stream_ending_early_is_truncated_even_when_ffmpeg_is_quiet(self, tmp_path):
        vp = _processor()
        side = [(True, "", _meta("00:00:15.00"), 1), (True, "out_time_us=7400000\nprogress=end\n", "", 0)]
        with patch("core.video_processor.SubprocessSafety.run_with_timeout", side_effect=side):
            assert vp.check_video_health(_video(tmp_path)) is False
        assert vp.last_verdict.reason_code == "video_truncated"
        assert "7.4s" in vp.last_verdict.detail

    def test_small_shortfall_is_tolerated(self, tmp_path):
        vp = _processor()
        side = [(True, "", _meta("00:00:15.00"), 1), (True, "out_time_us=14200000\nprogress=end\n", "", 0)]
        with patch("core.video_processor.SubprocessSafety.run_with_timeout", side_effect=side):
            assert vp.check_video_health(_video(tmp_path)) is True
        assert vp.last_verdict.category == "healthy"

    def test_stream_read_requests_progress(self, tmp_path):
        vp = _processor()
        side = [(True, "", _meta("00:00:15.00"), 1), (True, "out_time_us=15000000\n", "", 0)]
        with patch("core.video_processor.SubprocessSafety.run_with_timeout", side_effect=side) as run:
            vp.check_video_health(_video(tmp_path))
        stream_cmd = run.call_args_list[1].args[0]
        assert "-progress" in stream_cmd and "pipe:1" in stream_cmd


# ---------------------------------------------------------------------------
# Archive sets
# ---------------------------------------------------------------------------


def _touch(folder: Path, *names: str) -> None:
    for name in names:
        (folder / name).write_bytes(b"x")


class TestArchiveSets:
    def test_complete_7z_split_set(self, tmp_path):
        _touch(tmp_path, "movie.7z.001", "movie.7z.002", "movie.7z.003")
        [s] = find_archive_sets(tmp_path)
        assert s.name == "movie.7z" and s.kind == "7z-split"
        assert s.first.name == "movie.7z.001" and not s.missing and len(s.volumes) == 3

    def test_7z_gap_is_reported(self, tmp_path):
        _touch(tmp_path, "clip.7z.001", "clip.7z.003")
        [s] = find_archive_sets(tmp_path)
        assert s.missing == ["clip.7z.002"]

    def test_7z_missing_first_volume(self, tmp_path):
        _touch(tmp_path, "clip.7z.002")
        [s] = find_archive_sets(tmp_path)
        assert s.first is None and s.missing == ["clip.7z.001"]

    def test_rar_part_gap_keeps_number_width(self, tmp_path):
        _touch(tmp_path, "show.part01.rar", "show.part02.rar", "show.part04.rar")
        [s] = find_archive_sets(tmp_path)
        assert s.name == "show.rar" and s.missing == ["show.part03.rar"]

    def test_old_style_rar_volumes(self, tmp_path):
        _touch(tmp_path, "film.rar", "film.r00", "film.r01", "film.r03")
        [s] = find_archive_sets(tmp_path)
        assert s.kind == "rar-volumes" and s.missing == ["film.r02"] and len(s.volumes) == 4

    def test_old_style_volumes_without_head(self, tmp_path):
        _touch(tmp_path, "film.r00", "film.r01")
        [s] = find_archive_sets(tmp_path)
        assert s.first is None and s.missing[0] == "film.rar"

    def test_separate_sets_in_one_folder(self, tmp_path):
        _touch(tmp_path, "a.7z", "b.7z.001", "b.7z.002", "c.rar", "d.part1.rar", "d.part2.rar", "notes.txt")
        names = sorted(s.name for s in find_archive_sets(tmp_path))
        assert names == ["a.7z", "b.7z", "c.rar", "d.rar"]

    @pytest.mark.parametrize(
        "stderr,status,code",
        [
            ("ERROR: Missing volume : clip.7z.002", "held", "archive_incomplete"),
            ("Unexpected end of archive", "held", "archive_incomplete"),
            ("Wrong password : x.mkv", "held", "archive_password"),
            ("CRC Failed : x.mkv", "failed", "archive_corrupt"),
            ("Data Error : x.mkv", "failed", "archive_corrupt"),
            ("something unusual", "held", "archive_extract_failed"),
        ],
    )
    def test_failure_classification(self, stderr, status, code):
        assert classify_extract_failure("", stderr, 2, 600)[:2] == (status, code)


class TestArchiveProcessing:
    @pytest.fixture
    def processor(self):
        p = ArchiveProcessor(Config())
        p.system_check.get_tool_command = Mock(return_value=["7z"])
        return p

    def test_incomplete_set_is_held_and_never_extracted(self, processor, tmp_path):
        _touch(tmp_path, "clip.7z.001", "clip.7z.003")
        with patch("core.archive_processor.SubprocessSafety.run_with_timeout") as run:
            assert processor.process_rar_files(tmp_path) is False
        run.assert_not_called()
        [o] = processor.last_outcomes
        assert (o.status, o.reason_code) == ("held", "archive_volume_missing")
        assert (tmp_path / "clip.7z.001").exists() and (tmp_path / "clip.7z.003").exists()

    def test_unlistable_archive_is_held_not_called_malicious(self, processor, tmp_path):
        _touch(tmp_path, "pack.7z")
        with patch(
            "core.archive_processor.SubprocessSafety.run_with_line_handler", return_value=(False, "", 2)
        ), patch("core.archive_processor.StateValidator.check_disk_space", return_value=True), patch(
            "core.archive_processor.log_error"
        ) as log_error:
            processor.process_rar_files(tmp_path)
        [o] = processor.last_outcomes
        assert (o.status, o.reason_code) == ("held", "archive_unlistable")
        assert not any("SECURITY" in str(c) for c in log_error.call_args_list)
        assert (tmp_path / "pack.7z").exists()

    def test_failed_extraction_keeps_volumes(self, processor, tmp_path):
        _touch(tmp_path, "pack.7z.001", "pack.7z.002")
        with patch.object(processor, "_validate_archive_paths", return_value=True), patch(
            "core.archive_processor.StateValidator.check_disk_space", return_value=True
        ), patch(
            "core.archive_processor.SubprocessSafety.run_with_timeout",
            return_value=(False, "", "Unexpected end of archive", 2),
        ):
            processor.process_rar_files(tmp_path)
        assert processor.last_outcomes[0].status == "held"
        assert (tmp_path / "pack.7z.001").exists() and (tmp_path / "pack.7z.002").exists()

    def test_only_the_extracted_set_is_removed(self, processor, tmp_path):
        _touch(tmp_path, "good.7z", "bad.7z.001", "bad.7z.003")
        with patch.object(processor, "_validate_archive_paths", return_value=True), patch(
            "core.archive_processor.StateValidator.check_disk_space", return_value=True
        ), patch("core.archive_processor.SubprocessSafety.run_with_timeout", return_value=(True, "", "", 0)):
            assert processor.process_rar_files(tmp_path) is True
        assert not (tmp_path / "good.7z").exists()
        assert (tmp_path / "bad.7z.001").exists() and (tmp_path / "bad.7z.003").exists()


class TestHeldFolders:
    def test_held_file_blocks_folder_removal(self, tmp_path):
        folder = tmp_path / "Broken.Set"
        folder.mkdir()
        _touch(folder, "clip.7z.001", "clip.7z.003")
        handler = FileHandler(Config())
        assert handler.is_folder_empty_or_removable(folder, archive_error=True) is True
        handler.hold_paths([folder / "clip.7z.001"], "archive_volume_missing")
        assert handler.is_folder_empty_or_removable(folder, archive_error=True) is False
        assert handler.safe_delete_folder(folder, archive_error=True) is False
        assert folder.exists()


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------


def _fake_app(dry_run: bool, **overrides):
    stats = {
        k: 0
        for k in (
            "videos_moved",
            "videos_healthy",
            "videos_corrupt",
            "videos_failed",
            "videos_sample",
            "rars_extracted",
        )
    }
    app = types.SimpleNamespace(dry_run=dry_run, dry_run_plan=None, stats=stats, **overrides)
    return bind_app_helpers(app)


class TestAppWiring:
    def test_live_preview_is_counted_as_sample_and_removed(self, tmp_path):
        video = _video(tmp_path)
        vp = _processor()
        deleted = []
        app = _fake_app(
            False,
            video_processor=vp,
            file_handler=types.SimpleNamespace(
                wait_for_file_release=lambda *_: True,
                delete_video_file_with_retry=lambda v: deleted.append(v),
            ),
        )
        with patch(
            "core.video_processor.SubprocessSafety.run_with_timeout",
            return_value=(True, "", _meta("00:00:05.00"), 1),
        ):
            assert app._handle_video(video, tmp_path / "dst") is False
        assert app.stats["videos_sample"] == 1 and app.stats["videos_corrupt"] == 0
        assert deleted == [video]

    def test_dry_run_reports_preview_as_delete(self, tmp_path):
        video = _video(tmp_path)
        plan = Mock()
        vp = _processor()
        app = _fake_app(True, video_processor=vp)
        app.dry_run_plan = plan
        with patch(
            "core.video_processor.SubprocessSafety.run_with_timeout",
            return_value=(True, "", _meta("00:00:08.00"), 1),
        ):
            assert app._handle_video(video, tmp_path / "dst") is False
        plan.add_video_delete.assert_called_once()
        assert "preview" in plan.add_video_delete.call_args.args[1]
        plan.add_video_move.assert_not_called()

    def test_held_archive_becomes_run_error(self, tmp_path):
        _touch(tmp_path, "clip.7z.001", "clip.7z.003")
        processor = ArchiveProcessor(Config())
        held = []
        app = _fake_app(
            False,
            archive_processor=processor,
            file_handler=types.SimpleNamespace(hold_paths=lambda paths, reason: held.append((paths, reason))),
        )
        archive_error, count = app._process_archives(tmp_path)
        assert archive_error is True and count == 1
        assert held and held[0][1] == "archive_volume_missing"
        assert app.run_errors and "archive_volume_missing" in app.run_errors[0]

    def test_dry_run_flags_incomplete_set_once(self, tmp_path):
        _touch(tmp_path, "movie.7z.001", "movie.7z.002", "clip.7z.001", "clip.7z.003")
        plan = Mock()
        app = _fake_app(True, archive_processor=ArchiveProcessor(Config()))
        app.dry_run_plan = plan
        app._process_archives(tmp_path)
        assert plan.add_archive_extract.call_count == 1  # one entry per set, not per volume
        assert plan.add_archive_skip.call_count == 1
        assert "missing clip.7z.002" in plan.add_archive_skip.call_args.args[1]

    def test_finish_issues_warns_when_no_video_is_kept(self):
        app = _fake_app(False)
        app.stats.update(videos_sample=2, videos_corrupt=1, videos_moved=0)
        errors, warnings = app.finish_issues()
        assert errors == [] and any("no_videos_kept" in w for w in warnings)


# ---------------------------------------------------------------------------
# End to end with real tools (the scenarios from the issue reports)
# ---------------------------------------------------------------------------

SEVENZ = shutil.which("7zz") or shutil.which("7z")
FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(not (SEVENZ and FFMPEG), reason="needs 7-Zip and ffmpeg")
def test_end_to_end_previews_truncation_and_incomplete_sets(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    def make(path: Path, seconds: int) -> None:
        subprocess.run(
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=duration={seconds}:size=640x360:rate=30",
             "-c:v", "libx264", "-b:v", "3M", "-y", str(path)],
            check=True,
        )  # fmt: skip

    good = src / "Good.Movie"
    good.mkdir()
    make(good / "Good.Movie.mkv", 14)
    preview = src / "Preview.Clip"
    preview.mkdir()
    make(preview / "Preview.Clip.mkv", 6)
    trunc = src / "Cut.Short"
    trunc.mkdir()
    make(trunc / "Cut.Short.mkv", 14)
    data = (trunc / "Cut.Short.mkv").read_bytes()
    (trunc / "Cut.Short.mkv").write_bytes(data[: len(data) // 2])
    broken = src / "Broken.Set"
    broken.mkdir()
    make(tmp_path / "inner.mkv", 14)
    subprocess.run([SEVENZ, "a", "-v1m", "-mx0", str(broken / "clip.7z"), str(tmp_path / "inner.mkv")],
                   check=True, capture_output=True)  # fmt: skip
    volumes = sorted(broken.iterdir())
    assert len(volumes) >= 3
    volumes[1].unlink()

    config = tmp_path / "config.json"
    config.write_text(json.dumps({"min_sample_size_mb": 1, "log_folder": str(tmp_path / "logs")}))
    result = subprocess.run(
        [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--json", "--no-color"],
        capture_output=True, text=True, timeout=300, cwd=REPO,
    )  # fmt: skip
    summary = json.loads(result.stdout[result.stdout.index("{") :])

    assert result.returncode == unpackr.EXIT_COMPLETED_WITH_ERRORS, result.stdout[-2000:]
    assert summary["status"] == "completed_with_errors"
    assert [p.name for p in dst.iterdir()] == ["Good.Movie.mkv"]
    assert summary["counts"]["videos_sample"] == 1  # the 6 second preview, not "corrupt"
    assert summary["counts"]["videos_corrupt"] == 1  # the truncated file
    assert broken.exists() and len(list(broken.iterdir())) == len(volumes) - 1
    assert any("archive_volume_missing" in e for e in summary["errors"])
    assert not any("traversal" in e for e in summary["errors"])
