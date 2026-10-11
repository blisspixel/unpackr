"""
Issue #21: PAR2 never removes unextracted volumes, how unfinished and broken downloads are cleaned,
unfinished downloads, dry-run/live parity, and the smaller findings from that report.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.archive_processor import (
    ArchiveProcessor,
    classify_par2_result,
    is_archive_related,
    par2_set_heads,
    par2_set_name,
)
from core.config import Config
from core.safety_invariants import FileOperation, OperationType, SafetyInvariants, is_archive_volume

REPO = Path(__file__).resolve().parent.parent
SEVENZ = shutil.which("7zz") or shutil.which("7z")
PAR2 = shutil.which("par2")
FFMPEG = shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# Unit level
# ---------------------------------------------------------------------------


class TestPar2Classification:
    @pytest.mark.parametrize("code", [1, 2, 4, 5])
    def test_data_exit_codes_mean_damaged(self, code):
        assert classify_par2_result("", "", code, False)[0] == "damaged"

    @pytest.mark.parametrize("code", [3, 6, 7, 8, 9])
    def test_other_exit_codes_are_tool_errors(self, code):
        assert classify_par2_result("", "", code, False)[0] == "error"

    def test_repair_and_verify(self):
        assert classify_par2_result("Repair complete.", "", 0, True)[0] == "repaired"
        assert classify_par2_result("All files are correct", "", 0, True)[0] == "verified"

    def test_failure_text_wins_over_exit_zero(self):
        assert classify_par2_result("Repair is not possible.", "", 0, True)[0] == "damaged"

    def test_set_grouping(self, tmp_path):
        names = ["Movie.par2", "Movie.vol00+01.par2", "movie.vol01+02.PAR2", "Other.vol03+04.par2"]
        for n in names:
            (tmp_path / n).write_text("x")
        assert par2_set_name("Movie.vol00+01.par2") == "movie"
        heads = [p.name for p in par2_set_heads([tmp_path / n for n in names])]
        assert heads == ["Movie.par2", "Other.vol03+04.par2"]


class TestArchiveInvariantI3:
    @pytest.mark.parametrize(
        "name", ["x.rar", "x.r00", "x.r123", "x.7z", "x.7z.001", "x.part02.rar", "x.zip", "x.z01", "x.001", "x.par2"]
    )
    def test_split_volumes_are_refused_without_verified_extraction(self, tmp_path, name):
        invariants = SafetyInvariants(tmp_path)
        op = FileOperation(OperationType.DELETE, tmp_path / name)
        assert is_archive_volume(op.path)
        assert invariants.never_delete_archives_before_validation(op, extraction_verified=False) is False
        assert invariants.never_delete_archives_before_validation(op, extraction_verified=True) is True

    def test_videos_are_not_archive_volumes(self, tmp_path):
        assert not is_archive_volume(tmp_path / "movie.mkv")
        assert not is_archive_related(tmp_path / "movie.mkv")


def test_bundled_config_treats_ts_and_m2ts_as_video():
    config = Config(REPO / "config_files" / "config.json")
    assert {".ts", ".m2ts"} <= set(config.video_extensions)


def test_par2_unavailable_still_extracts(tmp_path):
    """Without par2, a release with .par2 files is not blocked: 7-Zip's CRC check decides."""
    processor = ArchiveProcessor(Config())
    (tmp_path / "set.par2").write_text("x")
    processor.system_check.get_tool_command = Mock(side_effect=lambda tool: [] if tool == "par2" else ["7z"])
    assert processor.process_par2_files(tmp_path) is False
    assert processor.last_par2.status == "unavailable"
    assert (tmp_path / "set.par2").exists()


@pytest.mark.parametrize("status", ["unavailable", "error"])
def test_unjudged_par2_release_keeps_unrecognised_files(tmp_path, status):
    """par2 could not judge the data: possible renamed volumes are held, not cleaned up as junk."""
    from types import SimpleNamespace

    from conftest import bind_app_helpers

    import unpackr
    from core.archive_processor import Par2Outcome

    folder = tmp_path / "Movie.2026"
    folder.mkdir()
    for name in ("Movie.2026.par2", "Movie.2026.vol00+01.par2", "0a30744ef547b49f", "1b27e21e42e11651"):
        (folder / name).write_bytes(b"x")
    (folder / "movie.nfo").write_text("nfo")
    held: dict = {}
    app = SimpleNamespace(
        dry_run=False,
        config=Config(),
        file_handler=SimpleNamespace(hold_paths=lambda paths, reason: held.update({p.name: reason for p in paths})),
        archive_processor=SimpleNamespace(remove_par2_files=Mock()),
    )
    bind_app_helpers(app)

    reason = f"par2_{'unavailable' if status == 'unavailable' else 'tool_error'}"
    keep = unpackr.UnpackrApp._finish_par2(app, folder, Par2Outcome(status, reason, "x"), False, False)

    assert keep is True
    assert set(held) == {"Movie.2026.par2", "Movie.2026.vol00+01.par2", "0a30744ef547b49f", "1b27e21e42e11651"}
    assert not app.archive_processor.remove_par2_files.called
    assert any(reason in e for e in app.run_errors)


def test_par2_damage_without_archives_is_junk_for_redownload(tmp_path):
    from types import SimpleNamespace

    from conftest import bind_app_helpers

    import unpackr
    from core.archive_processor import Par2Outcome

    folder = tmp_path / "Broken"
    folder.mkdir()
    app = SimpleNamespace(
        dry_run=False, config=Config(), file_handler=SimpleNamespace(), archive_processor=SimpleNamespace()
    )
    bind_app_helpers(app)

    keep = unpackr.UnpackrApp._finish_par2(
        app, folder, Par2Outcome("damaged", "par2_damaged", "x.par2: damaged"), False, False
    )

    assert keep is True  # par2_error: the folder's leftovers are junk to the cleanup step
    assert app.damaged and "Broken" in app.damaged[0]
    assert not app.run_errors


# ---------------------------------------------------------------------------
# End to end with real tools
# ---------------------------------------------------------------------------


def _video(path: Path, seconds: int = 14) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=duration={seconds}:size=320x240:rate=25",
         "-c:v", "libx264", "-b:v", "2M", "-y", str(path)],
        check=True,
    )  # fmt: skip


def _age(root: Path, seconds: int = 3600) -> None:
    """Make every file and folder under root look untouched for a while."""
    old = time.time() - seconds
    for current, dirs, files in os.walk(root):
        for name in dirs + files:
            os.utime(Path(current) / name, (old, old))
    os.utime(root, (old, old))


def _run(src: Path, dst: Path, tmp_path: Path, *extra: str, config: dict | None = None) -> tuple[int, dict]:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"min_sample_size_mb": 1, "log_folder": str(tmp_path / "logs"), **(config or {})}))
    result = subprocess.run(
        [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(cfg),
         "--json", "--no-color", *extra],
        capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    # stdout is the JSON summary and nothing else.
    return result.returncode, json.loads(result.stdout)


def _obfuscated_release(folder: Path, tmp_path: Path) -> None:
    """A healthy 3-volume 7z set protected by PAR2, with every volume renamed to random hex."""
    _video(tmp_path / "work" / "Movie.2026.mkv")
    folder.mkdir(parents=True)
    subprocess.run(
        [SEVENZ, "a", "-v300k", "-mx0", str(folder / "Movie.2026.7z"), str(tmp_path / "work" / "Movie.2026.mkv")],
        check=True, capture_output=True,
    )  # fmt: skip
    volumes = sorted(folder.glob("Movie.2026.7z.*"))
    assert len(volumes) >= 2
    subprocess.run(
        [PAR2, "c", "-q", "-r10", "Movie.2026.par2", *[v.name for v in volumes]],
        check=True, capture_output=True, cwd=folder,
    )  # fmt: skip
    for v in volumes:
        v.rename(folder / secrets.token_hex(8))


needs_tools = pytest.mark.skipif(not (SEVENZ and PAR2 and FFMPEG), reason="needs 7-Zip, par2 and ffmpeg")


@needs_tools
@pytest.mark.parametrize("delete_mode", ["quarantine", "permanent"])
def test_obfuscated_healthy_release_is_repaired_and_extracted(tmp_path, delete_mode):
    src, dst = tmp_path / "src", tmp_path / "dst"
    dst.mkdir()
    _obfuscated_release(src / "Movie.2026", tmp_path)
    _age(src)

    code, summary = _run(src, dst, tmp_path, config={"delete_mode": delete_mode})

    assert code == 0, summary
    assert [p.name for p in dst.rglob("*.mkv")] == ["Movie.2026.mkv"]
    assert not (src / "Movie.2026").exists()


@needs_tools
def test_release_par2_cannot_repair_is_junk_and_reported(tmp_path):
    """PAR2 scanned every file and says the data is gone: a broken download, removed like any
    damaged video (to quarantine by default) and listed for re-download."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    dst.mkdir()
    folder = src / "Broken.2026"
    _obfuscated_release(folder, tmp_path)
    # Damage beyond what 10% recovery can fix: cut two volumes down to almost nothing.
    for victim in sorted(p for p in folder.iterdir() if p.suffix != ".par2")[:2]:
        with open(victim, "r+b") as handle:
            handle.truncate(1000)
    count = len(list(folder.iterdir()))
    _age(src)

    code, summary = _run(src, dst, tmp_path)

    assert code == 0, summary
    assert not list(dst.rglob("*.mkv"))
    assert any("Broken.2026" in d for d in summary["damaged"])
    assert summary["removal"]["quarantined_files"] == count  # every file restorable
    assert not folder.exists()


@needs_tools
@pytest.mark.skipif(
    sys.platform != "linux", reason="hides par2 by narrowing PATH; macOS also finds it in Homebrew's folders"
)
def test_obfuscated_release_without_par2_is_kept(tmp_path):
    """No par2 to match renamed volumes: the unrecognised files are kept, not cleaned as junk."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    dst.mkdir()
    folder = src / "Movie.2026"
    _obfuscated_release(folder, tmp_path)
    before = sorted(p.name for p in folder.iterdir())
    _age(src)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in (SEVENZ, FFMPEG, shutil.which("ffprobe")):
        if tool:
            (bin_dir / Path(tool).name).symlink_to(tool)

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"log_folder": str(tmp_path / "logs")}))
    result = subprocess.run(
        [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(cfg),
         "--json", "--no-color"],
        capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
        env={**os.environ, "PATH": str(bin_dir)},
    )  # fmt: skip
    summary = json.loads(result.stdout)

    assert result.returncode == 3, summary
    assert sorted(p.name for p in folder.iterdir()) == before
    assert any("par2_unavailable" in e for e in summary["errors"])


@pytest.mark.skipif(not SEVENZ, reason="needs 7-Zip")
def test_header_encrypted_archive_is_junk(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "Locked").mkdir(parents=True)
    dst.mkdir()
    (tmp_path / "a.txt").write_text("hi")
    subprocess.run(
        [SEVENZ, "a", "-pSecret", "-mhe=on", str(src / "Locked" / "locked.7z"), str(tmp_path / "a.txt")],
        check=True, capture_output=True,
    )  # fmt: skip
    (src / "Locked" / "movie.mkv").write_bytes(b"\0" * 10)  # makes it a release worth processing
    _age(src)

    start = time.monotonic()
    code, summary = _run(src, dst, tmp_path)

    assert time.monotonic() - start < 120
    items = {i["path"]: i for i in summary["items"]}
    assert items["Locked/locked.7z"]["reason_code"] == "archive_password"
    # Running Unpackr means "clean now": an archive that cannot be opened is junk.
    assert code == 0
    assert items["Locked/locked.7z"]["action"] == "deleted"
    assert any("locked.7z" in d for d in summary["damaged"])
    assert not (src / "Locked").exists()


@pytest.mark.skipif(not (SEVENZ and FFMPEG), reason="needs 7-Zip and ffmpeg")
def test_dry_run_matches_live_run(tmp_path):
    """Same tree, dry run then live: the same pre-existing files get the same actions."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    dst.mkdir()
    _video(tmp_path / "work" / "Good.Movie.mkv")
    (tmp_path / "secret.txt").write_text("x")

    (src / "Good.Movie").mkdir(parents=True)
    subprocess.run([SEVENZ, "a", "-mx0", str(src / "Good.Movie" / "good.7z"), str(tmp_path / "work" / "Good.Movie.mkv")],
                   check=True, capture_output=True)  # fmt: skip
    (src / "Good.Movie" / "good.nfo").write_text("nfo")

    (src / "Missing.Volume").mkdir()
    subprocess.run([SEVENZ, "a", "-v200k", "-mx0", str(src / "Missing.Volume" / "mv.7z"),
                    str(tmp_path / "work" / "Good.Movie.mkv")], check=True, capture_output=True)  # fmt: skip
    (src / "Missing.Volume" / "mv.7z.002").unlink()

    (src / "Encrypted").mkdir()
    subprocess.run([SEVENZ, "a", "-pX", "-mhe=on", str(src / "Encrypted" / "enc.7z"), str(tmp_path / "secret.txt")],
                   check=True, capture_output=True)  # fmt: skip
    (src / "Encrypted" / "enc.nfo").write_text("nfo")

    (src / "Zipped").mkdir()
    subprocess.run([SEVENZ, "a", "-tzip", "-mx0", str(src / "Zipped" / "z.zip"), str(tmp_path / "work" / "Good.Movie.mkv")],
                   check=True, capture_output=True)  # fmt: skip

    (src / "Only.Junk").mkdir()
    (src / "Only.Junk" / "x.nfo").write_text("x")
    _age(src)

    _, planned = _run(src, dst, tmp_path, "--dry-run")
    _, live = _run(src, dst, tmp_path)

    def actions(summary: dict) -> dict:
        # Extracted members only exist during the live run; compare the files that were there before.
        return {
            i["path"]: (i["action"], i["reason_code"])
            for i in summary["items"]
            if not i["path"].endswith(".mkv") and not i.get("folder")
        }

    assert actions(planned) == actions(live)
    assert planned["counts"]["folders_deleted"] == live["counts"]["folders_deleted"]
    # A manual run treats sets that cannot be unpacked as junk; the dry run plans the same.
    assert not (src / "Missing.Volume").exists() and not (src / "Encrypted").exists()
    assert sorted(planned["damaged"]) == sorted(live["damaged"])


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
def test_manual_run_cleans_now(tmp_path):
    """Fresh files are processed right away and unfinished ones removed: running Unpackr means clean now."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    dst.mkdir()
    _video(src / "Fresh.Movie" / "Fresh.Movie.mkv")
    (src / "Fresh.Movie" / "Next.Episode.mkv.part").write_bytes(b"\0" * 100)

    code, summary = _run(src, dst, tmp_path)

    assert code == 0, summary
    assert [p.name for p in dst.rglob("*.mkv")] == ["Fresh.Movie.mkv"]
    items = {i["path"]: i for i in summary["items"]}
    assert items["Fresh.Movie/Next.Episode.mkv.part"]["reason_code"] == "download_incomplete"
    assert not (src / "Fresh.Movie").exists()
