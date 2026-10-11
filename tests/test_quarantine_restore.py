"""Tests for reversible removal: quarantine, trash, journal, restore and purge (issue #6)."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.config import Config
from core.file_handler import FileHandler
from core.remover import (
    QUARANTINE_DIR,
    RUNS_DIR,
    Remover,
    is_internal,
    list_runs,
    purge_quarantine,
    restore_run,
)
from doctor import UnpackrDoctor
from utils.cli_subcommands import run_subcommand
from utils.trash import send_to_trash

REPO = Path(__file__).resolve().parent.parent


def _hashes(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not is_internal(rel):
            out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _tree(root: Path, files: dict) -> None:
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class TestRemover:
    def test_quarantine_moves_and_journals(self, tmp_path):
        _tree(tmp_path, {"A/x.nfo": b"hello", "A/sub/y.sfv": b"crc"})
        remover = Remover("quarantine", source_root=tmp_path, run_id="20261010-120000")
        assert remover.remove(tmp_path / "A" / "x.nfo", "junk_extension") == "quarantine"
        assert remover.remove(tmp_path / "A" / "sub", "folder_cleanup") == "quarantine"
        qdir = tmp_path / QUARANTINE_DIR / "20261010-120000"
        assert (qdir / "A" / "x.nfo").read_bytes() == b"hello"
        assert (qdir / "A" / "sub" / "y.sfv").read_bytes() == b"crc"
        assert (remover.quarantined_files, remover.quarantined_bytes) == (2, 8)
        entries = [json.loads(line) for line in (tmp_path / RUNS_DIR / "20261010-120000.jsonl").read_text().splitlines()]
        assert [e["op"] for e in entries] == ["quarantined", "quarantined"]
        assert entries[0]["reason"] == "junk_extension"

    def test_quarantine_name_collision(self, tmp_path):
        remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
        for _ in range(2):
            (tmp_path / "a.txt").write_text("x")
            remover.remove(tmp_path / "a.txt", "junk")
        assert sorted(p.name for p in (tmp_path / QUARANTINE_DIR / "r1").iterdir()) == ["a.1.txt", "a.txt"]

    def test_permanent_mode_deletes(self, tmp_path):
        _tree(tmp_path, {"a.nfo": b"x"})
        remover = Remover("permanent", source_root=tmp_path, run_id="r1")
        assert remover.remove(tmp_path / "a.nfo", "junk") == "permanent"
        assert not (tmp_path / "a.nfo").exists()
        assert not (tmp_path / QUARANTINE_DIR).exists()

    def test_invalid_mode_and_missing_root(self, tmp_path):
        with pytest.raises(ValueError):
            Remover("shred", source_root=tmp_path)
        with pytest.raises(ValueError):
            Remover("quarantine")

    @pytest.mark.skipif(sys.platform.startswith("win") or sys.platform == "darwin", reason="freedesktop trash")
    def test_trash_mode_uses_freedesktop_trash(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        _tree(tmp_path, {"src/a b.nfo": b"x"})
        remover = Remover("trash", source_root=tmp_path / "src", run_id="r1")
        assert remover.remove(tmp_path / "src" / "a b.nfo", "junk") == "trash"
        trash = tmp_path / "data" / "Trash"
        assert (trash / "files" / "a b.nfo").read_bytes() == b"x"
        info = (trash / "info" / "a b.nfo.trashinfo").read_text()
        assert "Path=" in info and "a%20b.nfo" in info and "DeletionDate=" in info

    @pytest.mark.skipif(sys.platform.startswith("win") or sys.platform == "darwin", reason="freedesktop trash")
    def test_send_to_trash_collision(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        for _ in range(2):
            (tmp_path / "f.txt").write_text("x")
            send_to_trash(tmp_path / "f.txt")
        assert sorted(p.name for p in (tmp_path / "data" / "Trash" / "files").iterdir()) == ["f.2.txt", "f.txt"]


class TestFileHandlerUsesRemover:
    def test_folder_and_video_removal_go_to_quarantine(self, tmp_path):
        src = tmp_path / "src"
        _tree(src, {"Rel/a.nfo": b"1", "Rel/b.sfv": b"2", "Other/v.mkv": b"v" * 10})
        handler = FileHandler(Config())
        handler.remover = Remover("quarantine", source_root=src, run_id="r1")
        assert handler.safe_delete_folder(src / "Rel") is True
        assert handler.delete_video_file_with_retry(src / "Other" / "v.mkv", reason_code="video_truncated") is True
        q = src / QUARANTINE_DIR / "r1"
        assert (q / "Rel" / "a.nfo").exists() and (q / "Other" / "v.mkv").exists()

    def test_empty_folder_is_removed_not_quarantined(self, tmp_path):
        (tmp_path / "empty").mkdir()
        handler = FileHandler(Config())
        handler.remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
        assert handler.safe_delete_folder(tmp_path / "empty") is True
        assert not (tmp_path / QUARANTINE_DIR / "r1" / "empty").exists()


class TestRestore:
    def test_restore_round_trip_and_moved_files(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        dst.mkdir()
        _tree(src, {"Movie/m.mkv": b"movie" * 100, "Movie/m.nfo": b"nfo", "Junk/x.sfv": b"s"})
        before = _hashes(src)
        handler = FileHandler(Config())
        handler.remover = Remover("quarantine", source_root=src, run_id="r1")
        assert handler.move_file(src / "Movie" / "m.mkv", dst)
        assert handler.safe_delete_folder(src / "Movie")
        assert handler.safe_delete_folder(src / "Junk")
        assert _hashes(src) == {}

        preview = restore_run(src, "r1", dry_run=True)
        assert len(preview.restored) == 3 and _hashes(src) == {}

        result = restore_run(src, "r1")
        assert result.skipped == []
        assert _hashes(src) == before
        assert list(dst.iterdir()) == []

    def test_restore_skips_changed_destination_and_occupied_paths(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        dst.mkdir()
        _tree(src, {"A/v.mkv": b"v" * 50, "B/n.nfo": b"n"})
        handler = FileHandler(Config())
        handler.remover = Remover("quarantine", source_root=src, run_id="r1")
        handler.move_file(src / "A" / "v.mkv", dst)
        handler.remover.remove(src / "B" / "n.nfo", "junk")
        (dst / "v.mkv").write_bytes(b"changed")
        (src / "B" / "n.nfo").write_bytes(b"new")
        result = restore_run(src, "r1")
        assert result.restored == []
        assert any("changed since the run" in s for s in result.skipped)
        assert any("already exists" in s for s in result.skipped)

    def test_restore_path_filter_and_listing(self, tmp_path):
        _tree(tmp_path, {"A/a.nfo": b"a", "B/b.nfo": b"b"})
        remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
        remover.remove(tmp_path / "A" / "a.nfo", "junk")
        remover.remove(tmp_path / "B" / "b.nfo", "junk")
        [info] = list_runs(tmp_path)
        assert info.run_id == "r1" and info.counts == {"quarantined": 2} and info.quarantine_files == 2
        result = restore_run(tmp_path, "r1", path_glob="*/A/*")
        assert len(result.restored) == 1 and (tmp_path / "A" / "a.nfo").exists()
        assert not (tmp_path / "B" / "b.nfo").exists()

    def test_restore_refuses_journal_pointing_outside_quarantine(self, tmp_path):
        outside = tmp_path / "elsewhere.txt"
        outside.write_text("x")
        runs = tmp_path / "src" / RUNS_DIR
        runs.mkdir(parents=True)
        (runs / "r1.jsonl").write_text(
            json.dumps({"op": "quarantined", "src": str(tmp_path / "src" / "a.txt"), "dst": str(outside)}) + "\n"
        )
        result = restore_run(tmp_path / "src", "r1")
        assert result.restored == [] and outside.exists()

    def test_missing_journal(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            restore_run(tmp_path, "nope")


class TestPurge:
    def test_purge_only_old_runs_inside_quarantine(self, tmp_path):
        q = tmp_path / QUARANTINE_DIR
        old_id = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d-%H%M%S")
        new_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        _tree(q, {f"{old_id}/a.mkv": b"x" * 10, f"{new_id}/b.mkv": b"y"})
        keep = tmp_path / "Real.Folder" / "keep.mkv"
        _tree(tmp_path, {"Real.Folder/keep.mkv": b"z"})
        os.utime(keep, (0, 0))
        assert purge_quarantine(tmp_path, 14) == (1, 10)
        assert not (q / old_id).exists() and (q / new_id).exists() and keep.exists()
        assert purge_quarantine(tmp_path, 0) == (0, 0)

    def test_purge_never_follows_a_symlinked_quarantine(self, tmp_path):
        target = tmp_path / "precious"
        _tree(target, {"19990101-000000/a": b"x"})
        (tmp_path / "src").mkdir()
        try:
            (tmp_path / "src" / QUARANTINE_DIR).symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks not permitted here")
        assert purge_quarantine(tmp_path / "src", 1) == (0, 0)
        assert (target / "19990101-000000" / "a").exists()


class TestCliAndDoctor:
    def test_runs_and_restore_subcommands(self, tmp_path, capsys):
        _tree(tmp_path, {"A/a.nfo": b"a"})
        Remover("quarantine", source_root=tmp_path, run_id="20261010-120000").remove(tmp_path / "A" / "a.nfo", "junk")
        assert run_subcommand(["runs", "--source", str(tmp_path)]) == 0
        assert "20261010-120000" in capsys.readouterr().out
        assert run_subcommand(["restore", "latest", "--source", str(tmp_path), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["run_id"] == "20261010-120000" and len(payload["restored"]) == 1
        assert (tmp_path / "A" / "a.nfo").exists()
        assert run_subcommand(["restore", "missing", "--source", str(tmp_path)]) == 1

    def test_doctor_reports_quarantine_and_warns_when_large(self, tmp_path, capsys):
        _tree(tmp_path, {"A/a.mkv": b"x" * (2 * 1024 * 1024)})
        Remover("quarantine", source_root=tmp_path, run_id="r1").remove(tmp_path / "A" / "a.mkv", "junk")
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"quarantine_warn_mb": 1}))
        doctor = UnpackrDoctor(cfg, source=tmp_path)
        doctor.check_quarantine()
        assert any("Quarantine holds" in w for w in doctor.warnings)

    def test_config_validates_delete_mode(self, tmp_path):
        cfg = tmp_path / "c.json"
        cfg.write_text(json.dumps({"delete_mode": "shred"}))
        assert Config(cfg).is_valid is False
        cfg.write_text(json.dumps({"delete_mode": "trash", "quarantine_retention_days": 0}))
        config = Config(cfg)
        assert config.is_valid and config.delete_mode == "trash" and config.quarantine_retention_days == 0


# ---------------------------------------------------------------------------
# End to end: the #2 fixture with defaults is fully recoverable
# ---------------------------------------------------------------------------

FFMPEG = shutil.which("ffmpeg")
SEVENZ = shutil.which("7zz") or shutil.which("7z")


@pytest.mark.skipif(not (FFMPEG and SEVENZ), reason="needs ffmpeg and 7-Zip")
def test_default_run_is_fully_restorable(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    for folder, seconds in (("Loose.D", 8), ("Real.Movie", 14)):
        (src / folder).mkdir()
        subprocess.run(
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=duration={seconds}:size=640x360:rate=30",
             "-c:v", "libx264", "-b:v", "3M", "-y", str(src / folder / f"{folder}.mkv")],
            check=True,
        )  # fmt: skip
        (src / folder / f"{folder}.nfo").write_text("info")
    before = _hashes(src)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"min_sample_size_mb": 1, "log_folder": str(tmp_path / "logs")}))

    result = subprocess.run(
        [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--json", "--no-color"],
        capture_output=True, text=True, timeout=300, cwd=REPO,
    )  # fmt: skip
    summary = json.loads(result.stdout[result.stdout.index("{") :])
    assert result.returncode == 0, result.stdout[-2000:]
    assert summary["removal"]["mode"] == "quarantine"
    assert summary["removal"]["quarantined_files"] >= 3  # the preview, and both .nfo files
    assert any("unpackr restore" in a for a in summary["recommended_actions"])
    deleted = [i for i in summary["items"] if i["action"] == "deleted"]
    assert deleted and all(i["disposal"] == "quarantine" for i in deleted)
    assert [p.name for p in dst.iterdir()] == ["Real.Movie.mkv"]
    assert _hashes(src) == {}

    run_id = summary["removal"]["run_id"]
    restore = subprocess.run(
        [sys.executable, "unpackr.py", "restore", run_id, "--source", str(src)],
        capture_output=True, text=True, timeout=120, cwd=REPO,
    )  # fmt: skip
    assert restore.returncode == 0, restore.stdout
    assert _hashes(src) == before
    assert list(dst.iterdir()) == []
