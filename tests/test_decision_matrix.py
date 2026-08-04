"""
Archive and video decision matrices.

Reproducible classification tables for pre-scan folder roles, archive part
selection, sample-video removal, path containment, and sample-size edges.
Closes ROADMAP Correctness acceptance: "Archive/video decision paths are
reproducibly testable."
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Iterable
from unittest.mock import Mock, patch

import pytest

from core.archive_processor import ArchiveProcessor
from core.config import Config
from core.video_processor import VideoProcessor
from unpackr import UnpackrApp
from utils import filesystem_policy as fsp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_source(source: Path, config: Config | None = None):
    app = UnpackrApp.__new__(UnpackrApp)  # type: ignore[misc]
    app.config = config or Config()
    app.work_plan = None
    return UnpackrApp.scan_and_plan(app, source)


def _role(plan, name: str) -> str:
    if any(Path(item["path"]).name == name for item in plan.video_folders):
        return "video"
    if any(Path(item["path"]).name == name for item in plan.content_folders):
        return "content"
    if any(Path(p).name == name for p in plan.junk_folders):
        return "junk"
    return "missing"


def _touch(folder: Path, names: Iterable[str], size: int = 32) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    payload = b"x" * size
    for name in names:
        (folder / name).write_bytes(payload)


# ---------------------------------------------------------------------------
# Pre-scan: archive/video folder classification
# ---------------------------------------------------------------------------


class TestPreScanArchiveVideoMatrix:
    """Which file markers force a folder into the video-work plan."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("movie.mkv", "video"),
            ("movie.mp4", "video"),
            ("release.rar", "video"),
            ("release.part001.rar", "video"),
            ("release.r00", "video"),
            ("release.r99", "video"),
            ("pack.7z", "video"),
            ("pack.7z.001", "video"),
            ("only.par2", "junk"),  # PAR2 alone does not mark video work
            ("readme.nfo", "junk"),
            ("track.mp3", "junk"),  # below music threshold
        ],
    )
    def test_single_marker_classification(self, tmp_path, filename, expected):
        source = tmp_path / "src"
        source.mkdir()
        folder = source / "item"
        _touch(folder, [filename])

        plan = _scan_source(source)
        assert _role(plan, "item") == expected

    def test_multipart_rar_counts_as_video_work(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        folder = source / "set"
        _touch(
            folder,
            [
                "show.part001.rar",
                "show.part002.rar",
                "show.part003.rar",
                "show.par2",
            ],
        )
        plan = _scan_source(source)
        assert _role(plan, "set") == "video"
        entry = next(v for v in plan.video_folders if Path(v["path"]).name == "set")
        assert entry["rars"] >= 1
        assert entry["par2s"] >= 1

    def test_video_plus_archive_is_video_not_junk(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        folder = source / "combo"
        _touch(folder, ["movie.mkv", "extra.rar"])
        plan = _scan_source(source)
        assert _role(plan, "combo") == "video"


# ---------------------------------------------------------------------------
# Archive part selection (what 7z is asked to extract)
# ---------------------------------------------------------------------------


class TestArchivePartSelectionMatrix:
    @pytest.fixture
    def processor(self):
        config = Config()
        proc = ArchiveProcessor(config)
        proc.system_check.get_tool_command = Mock(return_value=["7z"])
        return proc

    def _extracted_names(self, processor, folder: Path) -> list[str]:
        names: list[str] = []
        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch(
                "core.archive_processor.SubprocessSafety.run_with_timeout",
                return_value=(True, "", "", 0),
            ) as mock_run:
                processor.process_rar_files(folder)
                for call in mock_run.call_args_list:
                    args = call.args[0] if call.args else call[0][0]
                    # command: [7z, "x", archive, "-o...", "-aoa"]
                    for token in args:
                        token_s = str(token)
                        lower = token_s.lower()
                        if lower.endswith(".rar") or lower.endswith(".7z") or ".7z." in lower:
                            names.append(Path(token_s).name)
                            break
        return names

    def test_only_first_rar_parts_extracted(self, processor, tmp_path):
        folder = tmp_path / "rarset"
        folder.mkdir()
        for name in (
            "a.part001.rar",
            "a.part002.rar",
            "a.part003.rar",
            "b.part01.rar",
            "b.part02.rar",
            "c.part1.rar",
            "c.part2.rar",
            "solo.rar",
        ):
            (folder / name).write_bytes(b"x")

        extracted = set(self._extracted_names(processor, folder))
        assert extracted == {"a.part001.rar", "b.part01.rar", "c.part1.rar", "solo.rar"}

    def test_7z_only_base_and_001(self, processor, tmp_path):
        folder = tmp_path / "7zset"
        folder.mkdir()
        for name in ("pack.7z", "split.7z.001", "split.7z.002", "split.7z.100"):
            (folder / name).write_bytes(b"x")

        extracted = set(self._extracted_names(processor, folder))
        assert extracted == {"pack.7z", "split.7z.001"}
        assert "split.7z.002" not in extracted
        assert "split.7z.100" not in extracted


# ---------------------------------------------------------------------------
# Sample video removal decisions
# ---------------------------------------------------------------------------


class TestSampleVideoRemovalMatrix:
    def _app(self, dry_run: bool = False):
        return SimpleNamespace(
            stats={"videos_sample": 0},
            dry_run=dry_run,
            dry_run_plan=None,
        )

    @pytest.mark.parametrize(
        "sample_name,full_name,should_remove",
        [
            ("Movie.Sample.mkv", "Movie.mkv", True),
            ("Movie-sample.mkv", "Movie.mkv", True),
            ("Movie_preview.mkv", "Movie.mkv", True),
            ("Movie-trailer.mkv", "Movie.mkv", True),
            ("Movie-promo.mkv", "Movie.mkv", True),
            ("Unrelated-sample.mkv", "OtherShow.mkv", False),
            ("Movie.Sample.mkv", None, False),  # sample alone kept
        ],
    )
    def test_sample_removal_matrix(self, tmp_path, sample_name, full_name, should_remove):
        folder = tmp_path / "vids"
        folder.mkdir()
        sample = folder / sample_name
        sample.write_bytes(b"s" * 1024)
        videos = [sample]
        if full_name:
            full = folder / full_name
            full.write_bytes(b"f" * (50 * 1024))
            videos.append(full)

        app = self._app(dry_run=True)
        result = UnpackrApp._remove_sample_videos(app, videos)

        if should_remove:
            assert sample not in result
            assert app.stats["videos_sample"] == 1
        else:
            assert sample in result
            assert app.stats["videos_sample"] == 0


class TestVideoSampleSizeMatrix:
    @pytest.fixture
    def processor(self):
        return VideoProcessor(Config())

    def test_size_exactly_at_threshold_is_not_sample(self, processor, tmp_path):
        video = tmp_path / "edge.mp4"
        # Exactly 50 MiB: size_mb < 50 is sample; equality is full release
        video.write_bytes(b"x" * (50 * 1024 * 1024))
        assert processor.is_sample_file(video, min_size_mb=50) is False

    def test_size_one_byte_under_threshold_is_sample(self, processor, tmp_path):
        video = tmp_path / "under.mp4"
        video.write_bytes(b"x" * (50 * 1024 * 1024 - 1))
        assert processor.is_sample_file(video, min_size_mb=50) is True

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Show.SAMPLE.mkv", True),
            ("show.Sample.mp4", True),
            ("sample-of-show.mkv", True),
            ("Show.mkv", False),  # large file, no keyword
        ],
    )
    def test_filename_keyword_matrix(self, processor, tmp_path, name, expected):
        video = tmp_path / name
        video.write_bytes(b"x" * (100 * 1024 * 1024))
        assert processor.is_sample_file(video) is expected


# ---------------------------------------------------------------------------
# Archive member containment decisions
# ---------------------------------------------------------------------------


class TestContainmentDecisionMatrix:
    @pytest.mark.parametrize(
        "member,unsafe",
        [
            ("video.mkv", False),
            ("subdir/video.mkv", False),
            (r"subdir\video.mkv", False),
            ("../escape.mkv", True),
            ("..\\escape.mkv", True),
            ("/etc/passwd", True),
            (r"C:\Windows\evil.dll", True),
            ("//server/share/x", True),
            ("bad\x00name.mkv", True),
            ("", False),
        ],
    )
    def test_containment_table(self, tmp_path, member, unsafe):
        reason = fsp.containment_violation(member, tmp_path)
        if unsafe:
            assert reason is not None, f"expected unsafe for {member!r}"
        else:
            assert reason is None, f"expected safe for {member!r}, got {reason}"


# ---------------------------------------------------------------------------
# Video health early-reject decisions (no ffmpeg required)
# ---------------------------------------------------------------------------


class TestVideoHealthEarlyRejectMatrix:
    @pytest.fixture
    def processor(self):
        return VideoProcessor(Config())

    def test_under_1mb_rejected(self, processor, tmp_path):
        video = tmp_path / "tiny.mp4"
        video.write_bytes(b"x" * (512 * 1024))
        assert processor.check_video_health(video) is False

    def test_under_1mb_quality_tuple_rejected(self, processor, tmp_path):
        video = tmp_path / "tiny.mp4"
        video.write_bytes(b"x" * (512 * 1024))
        assert processor.check_video_health(video, check_quality=True) == (False, False, None, None)
