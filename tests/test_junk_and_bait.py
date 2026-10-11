"""Junk, bait, in-progress and sample rules (issues #12, #13, #14, #15)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from core.config import Config
from core.file_handler import FileHandler
from core.junk_rules import (
    classify_security,
    decide_release_samples,
    find_incomplete_markers,
    has_disc_structure,
    is_padding_file,
    junk_name_reason,
    looks_like_sample,
)

REPO = Path(__file__).resolve().parent.parent


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class TestSecurity:
    @pytest.mark.parametrize(
        "name,code,fails",
        [
            ("CD.lnk", "security_dangerous_ext", True),
            ("setup.exe", "security_executable", True),
            ("Movie.2026.1080p.mkv.exe", "security_double_extension", True),
            ("codec.scr", "security_dangerous_ext", True),
            ("RARBG_DO_NOT_MIRROR.exe", "security_known_marker", False),
            ("rename.bat", "security_rename_script", False),
        ],
    )
    def test_bait_classification(self, tmp_path, name, code, fails):
        finding = classify_security(_touch(tmp_path / name), Config(), release_has_video=True)
        assert finding is not None and (finding.reason_code, finding.fails_release) == (code, fails)

    def test_rename_script_without_video_still_fails(self, tmp_path):
        finding = classify_security(_touch(tmp_path / "rename.bat"), Config(), release_has_video=False)
        assert finding.fails_release

    def test_bidi_disguised_name(self, tmp_path):
        finding = classify_security(_touch(tmp_path / ("Movie" + chr(0x202E) + "vkm.exe")), Config(), True)
        assert finding.reason_code == "security_bidi_name"

    def test_subtitle_payloads(self, tmp_path):
        assert classify_security(_touch(tmp_path / "ok.srt", b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"), Config(), True) is None
        assert classify_security(_touch(tmp_path / "bin.srt", b"MZ\x00\x00payload"), Config(), True).reason_code == (
            "security_suspicious_subtitle"
        )
        assert classify_security(_touch(tmp_path / "big.srt", b"a" * (2 * 1024 * 1024)), Config(), True) is not None

    def test_plain_files_are_fine(self, tmp_path):
        for name in ("Movie.mkv", "Movie.nfo", "Movie.srt", "cover.jpg"):
            assert classify_security(_touch(tmp_path / name, b"text"), Config(), True) is None


class TestJunkNames:
    @pytest.mark.parametrize(
        "rel,code",
        [
            ("RARBG.txt", "junk_name"),
            ("WWW.YTS.MX.COM.jpg", "junk_name"),
            ("Thumbs.db", "junk_name"),
            (".DS_Store", "junk_name"),
            ("desktop.ini", "junk_name"),
            ("._Movie.mkv", "junk_name"),
            ("@eaDir/Movie.mkv@SynoEAStream", "junk_os_cruft"),
        ],
    )
    def test_names(self, tmp_path, rel, code):
        assert junk_name_reason(_touch(tmp_path / rel), Config()) == code

    def test_padding_needs_zero_content(self, tmp_path):
        name = "_____padding_file_0_if you see this file, please update to BitComet 0.85 or above____"
        assert is_padding_file(_touch(tmp_path / name, b"\0" * 4096))
        assert not is_padding_file(_touch(tmp_path / "other" / name, b"MZ" + b"\0" * 10))
        assert is_padding_file(_touch(tmp_path / ".pad" / "12345", b"\0" * 100))
        assert junk_name_reason(tmp_path / name, Config()) == "torrent_padding"

    def test_empty_file(self, tmp_path):
        assert junk_name_reason(_touch(tmp_path / "zero.bin", b""), Config()) == "empty_file"

    def test_folder_with_only_cruft_is_removable_and_partial_is_not(self, tmp_path):
        handler = FileHandler(Config())
        cruft = tmp_path / "cruft"
        _touch(cruft / "desktop.ini")
        _touch(cruft / ".DS_Store")
        _touch(cruft / "@eaDir" / "x@SynoResource")
        _touch(cruft / "_____padding_file_1_", b"\0" * 64)
        assert handler.is_folder_empty_or_removable(cruft)
        partial = tmp_path / "partial"
        _touch(partial / "movie.mkv.part")
        assert not handler.is_folder_empty_or_removable(partial)
        rar_parts = tmp_path / "parts"
        _touch(rar_parts / "show.part033.rar.1")
        assert handler.is_folder_empty_or_removable(rar_parts)


class TestInProgressAndDisc:
    def test_markers(self, tmp_path):
        _touch(tmp_path / "a" / "movie.mkv.!qB")
        _touch(tmp_path / "b.mkv.crdownload")
        _touch(tmp_path / "ok.mkv")
        assert {p.name for p in find_incomplete_markers(tmp_path)} == {"movie.mkv.!qB", "b.mkv.crdownload"}

    def test_disc_structure(self, tmp_path):
        _touch(tmp_path / "Movie" / "VIDEO_TS" / "VTS_01_1.VOB")
        assert has_disc_structure(tmp_path / "Movie").name == "VIDEO_TS"
        assert has_disc_structure(_touch(tmp_path / "Plain" / "a.mkv").parent) is None


class TestSamples:
    def test_name_and_folder_evidence(self, tmp_path):
        cfg = Config()
        assert looks_like_sample(tmp_path / "Release" / "Sample" / "x.mkv", cfg) == "sample_folder"
        assert looks_like_sample(tmp_path / "Movie-sample.mkv", cfg) == "sample_named"
        assert looks_like_sample(tmp_path / "Movie.Proof.mkv", cfg) == "sample_named"
        assert looks_like_sample(tmp_path / "Samplers.Documentary.mkv", cfg) is None

    def test_duration_cap_protects_long_named_videos(self, tmp_path):
        main = tmp_path / "Show.S01E01.mkv"
        promo = tmp_path / "Show.S01E02.Promo.Special.mkv"
        sample = tmp_path / "Sample" / "show-sample.mkv"
        durations = {main: 2700.0, promo: 2600.0, sample: 60.0}
        sizes = {main: 3_000_000_000, promo: 2_900_000_000, sample: 50_000_000}
        decided = decide_release_samples([main, promo, sample], durations, sizes, Config())
        assert set(decided) == {sample} and decided[sample][0] == "sample_folder"

    def test_relative_rule(self, tmp_path):
        main, extra = tmp_path / "Movie.mkv", tmp_path / "x9f3.mkv"
        decided = decide_release_samples([main, extra], {main: 6000.0, extra: 120.0}, {main: 1, extra: 1}, Config())
        assert decided[extra][0] == "sample_relative"

    def test_only_video_is_never_a_sample(self, tmp_path):
        only = tmp_path / "Sample" / "trailer.mkv"
        assert decide_release_samples([only], {only: 30.0}, {only: 1}, Config()) == {}

    def test_unknown_duration_needs_small_size(self, tmp_path):
        main, sample = tmp_path / "Movie.mkv", tmp_path / "Movie.sample.mkv"
        big = decide_release_samples([main, sample], {main: None, sample: None}, {main: 9e9, sample: 2e9}, Config())
        assert big == {}
        small = decide_release_samples([main, sample], {main: None, sample: None}, {main: 9e9, sample: 1e6}, Config())
        assert small[sample][0] == "sample_named"


# ---------------------------------------------------------------------------
# End to end: a hostile download folder
# ---------------------------------------------------------------------------

FFMPEG = shutil.which("ffmpeg")
SEVENZ = shutil.which("7zz") or shutil.which("7z")


@pytest.mark.skipif(not (FFMPEG and SEVENZ), reason="needs ffmpeg and 7-Zip")
def test_hostile_download_folder(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    dst.mkdir()

    def video(path: Path, seconds: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=duration={seconds}:size=320x240:rate=25",
             "-c:v", "libx264", "-b:v", "3M", "-y", str(path)],
            check=True,
        )  # fmt: skip

    video(src / "Bait.Release" / "Bait.Release.2026.mkv", 14)
    _touch(src / "Bait.Release" / "CD.lnk")
    video(src / "In.Progress" / "Done.Part.mkv", 14)
    _touch(src / "In.Progress" / "Second.Part.mkv.part")
    video(src / "With.Sample" / "With.Sample.mkv", 30)
    video(src / "With.Sample" / "Sample" / "with.sample-sample.mkv", 12)
    video(src / "Rarbg.Style" / "Rarbg.Style.mkv", 14)
    _touch(src / "Rarbg.Style" / "RARBG.txt", b"visit")
    _touch(src / "Rarbg.Style" / "RARBG_DO_NOT_MIRROR.exe", b"MZ")
    _touch(src / "Rarbg.Style" / "desktop.ini", b"[x]")
    _touch(src / "Rarbg.Style" / "_____padding_file_0_", b"\0" * 1024)
    _touch(src / "Disc.Movie" / "VIDEO_TS" / "VTS_01_1.VOB", b"\0" * 2048)
    video(tmp_path / "packed.mkv", 14)
    _touch(tmp_path / "setup.exe", b"MZ")
    (src / "Fake.Archive").mkdir(parents=True)
    subprocess.run([SEVENZ, "a", "-mx0", str(src / "Fake.Archive" / "fake.7z"), str(tmp_path / "packed.mkv"),
                    str(tmp_path / "setup.exe")], check=True, capture_output=True)  # fmt: skip

    config = tmp_path / "config.json"
    config.write_text(json.dumps({"min_sample_size_mb": 1, "log_folder": str(tmp_path / "logs")}))
    result = subprocess.run(
        [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--json", "--no-color"],
        capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    summary = json.loads(result.stdout)
    items = {i["path"]: i for i in summary["items"]}

    assert result.returncode == 3, result.stdout[-3000:]
    assert sorted(p.name for p in dst.iterdir()) == ["Done.Part.mkv", "Rarbg.Style.mkv", "With.Sample.mkv"]

    # Bait: decoy kept in place, payload quarantined, release failed.
    assert (src / "Bait.Release" / "Bait.Release.2026.mkv").exists()
    assert items["Bait.Release/CD.lnk"]["reason_code"] == "security_dangerous_ext"
    assert any("folder_failed_security" in e for e in summary["errors"])

    # A manual run means "clean now": the unfinished file is junk, the finished one is kept.
    assert not (src / "In.Progress" / "Second.Part.mkv.part").exists()
    assert items["In.Progress/Second.Part.mkv.part"]["reason_code"] == "download_incomplete"
    assert items["In.Progress/Done.Part.mkv"]["action"] == "moved"

    # Sample folder video removed, not moved.
    assert items["With.Sample/Sample/with.sample-sample.mkv"]["reason_code"] == "sample_folder"

    # RARBG style: marker exe quarantined without failing, junk cleaned, movie moved.
    assert items["Rarbg.Style/RARBG_DO_NOT_MIRROR.exe"]["reason_code"] == "security_known_marker"
    assert not (src / "Rarbg.Style").exists()

    # Disc structure kept whole; archive with an executable never extracted.
    assert (src / "Disc.Movie" / "VIDEO_TS" / "VTS_01_1.VOB").exists()
    assert items["Fake.Archive/fake.7z"]["reason_code"] == "archive_dangerous_member"
    assert not (src / "Fake.Archive" / "setup.exe").exists()


class TestDuplicateEncodes:
    def test_keeps_largest_copy_of_same_title(self, tmp_path):
        from core.junk_rules import decide_duplicate_encodes, normalized_title

        a = tmp_path / "Movie.2026.1080p.WEB-DL.x264-GRP.mkv"
        b = tmp_path / "Movie.2026.720p.HDTV.x265-OTHER.mkv"
        c = tmp_path / "Different.Film.2026.1080p.mkv"
        assert normalized_title(a) == normalized_title(b) == "movie 2026"
        decided = decide_duplicate_encodes([a, b, c], {a: 9_000, b: 3_000, c: 5_000})
        assert decided == {b: ("duplicate_encode", f"smaller copy of {a.name}")}

    def test_is_opt_in(self, tmp_path):
        assert Config().get("dedupe_same_title") is False
