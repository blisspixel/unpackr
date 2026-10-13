"""Tests for the per-file run report (issue #7)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from unpackr.core.run_report import RunReport
from unpackr.utils.run_summary import build_unpackr_run_summary

REPO = Path(__file__).resolve().parent.parent


def _tree(root: Path, files: dict) -> None:
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class TestRunReport:
    def test_inventory_skips_internal_state(self, tmp_path):
        _tree(tmp_path, {"a/x.nfo": b"1", ".unpackr-state.json": b"{}", ".unpackr-quarantine/r/a.mkv": b"x"})
        report = RunReport()
        report.begin(tmp_path)
        assert set(report._inventory) == {"a/x.nfo"}

    def test_latest_record_wins_and_unknown_action_rejected(self, tmp_path):
        _tree(tmp_path, {"a/v.mkv": b"xx"})
        report = RunReport()
        report.begin(tmp_path)
        report.record(tmp_path / "a/v.mkv", "kept", "first")
        report.record(tmp_path / "a/v.mkv", "moved", "video_ok", destination=Path("/dst/v.mkv"))
        [item] = report.items()
        assert (item.action, item.reason_code, item.folder, item.bytes) == ("moved", "video_ok", "a", 2)
        with pytest.raises(ValueError):
            report.record(tmp_path / "a/v.mkv", "vanished", "x")

    def test_finalize_reconciles_unrecorded_files(self, tmp_path):
        _tree(
            tmp_path,
            {"done/x.nfo": b"1", "done/x.par2": b"1", "keep/song.mp3": b"1", "gone/loose.sfv": b"1"},
        )
        report = RunReport()
        report.begin(tmp_path)
        shutil.rmtree(tmp_path / "done")
        report.record_folder_removed(tmp_path / "done", "processed_folder")
        (tmp_path / "gone/loose.sfv").unlink()
        items = {i.path: i for i in report.finalize([".nfo", ".sfv"])}
        assert items["done/x.nfo"].action == "deleted" and items["done/x.nfo"].reason_code == "junk_extension"
        assert items["done/x.par2"].reason_code == "par2_cleanup"
        assert items["keep/song.mp3"].action == "kept" and items["keep/song.mp3"].reason_code == "not_processed"
        assert items["gone/loose.sfv"].action == "deleted" and items["gone/loose.sfv"].inferred

    def test_failed_set_becomes_deleted_only_if_removed(self, tmp_path):
        _tree(tmp_path, {"a/x.7z": b"1", "b/y.7z": b"1"})
        report = RunReport()
        report.begin(tmp_path)
        report.record(tmp_path / "a/x.7z", "skipped", "archive_corrupt")
        report.record(tmp_path / "b/y.7z", "skipped", "archive_corrupt")
        (tmp_path / "a/x.7z").unlink()
        items = {i.path: i for i in report.finalize()}
        assert items["a/x.7z"].action == "deleted" and items["a/x.7z"].reason_code == "archive_corrupt"
        assert items["b/y.7z"].action == "skipped"

    def test_planned_report_uses_folder_plan_not_disk(self, tmp_path):
        _tree(tmp_path, {"junk/a.nfo": b"1", "keep/b.mp3": b"1"})
        report = RunReport(planned=True)
        report.begin(tmp_path)
        report.record_folder_removed(tmp_path / "junk", "junk_folder")
        items = {i.path: i for i in report.finalize([".nfo"])}
        assert items["junk/a.nfo"].action == "deleted" and items["junk/a.nfo"].planned
        assert items["keep/b.mp3"].action == "kept"

    def test_jsonl_and_summary_counts(self, tmp_path):
        _tree(tmp_path, {"a/v.mkv": b"1"})
        report = RunReport()
        report.begin(tmp_path)
        report.record(tmp_path / "a/v.mkv", "moved", "video_ok")
        items = report.finalize()
        out = tmp_path / "out" / "r.jsonl"
        RunReport.write_jsonl(items, out, summary={"status": "completed"})
        lines = [json.loads(line) for line in out.read_text().splitlines()]
        assert lines[0]["type"] == "item" and lines[0]["path"] == "a/v.mkv"
        assert lines[-1] == {"type": "summary", "status": "completed"}
        summary = build_unpackr_run_summary(status="completed", exit_code=0, items=[i.to_dict() for i in items])
        assert summary["item_counts"] == {"moved": 1}


# ---------------------------------------------------------------------------
# End to end: exactly one terminal action for every pre-existing file
# ---------------------------------------------------------------------------

SEVENZ = shutil.which("7zz") or shutil.which("7z")
FFMPEG = shutil.which("ffmpeg")


def _run(src: Path, dst: Path, config: Path, *extra: str) -> tuple:
    result = subprocess.run(
        [sys.executable, "-m", "unpackr", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--json", "--no-color", *extra],
        capture_output=True, text=True, timeout=300, cwd=REPO,
    )  # fmt: skip
    return result, json.loads(result.stdout[result.stdout.index("{") :])


@pytest.mark.skipif(not (SEVENZ and FFMPEG), reason="needs 7-Zip and ffmpeg")
def test_every_preexisting_file_has_exactly_one_terminal_action(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    def make(path: Path, seconds: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=duration={seconds}:size=640x360:rate=30",
             "-c:v", "libx264", "-b:v", "3M", "-y", str(path)],
            check=True,
        )  # fmt: skip

    make(src / "Movie.One" / "Movie.One.mkv", 14)
    (src / "Movie.One" / "Movie.One.nfo").write_text("info")
    (src / "Movie.One" / "Movie.One.sfv").write_text("crc")
    make(src / "Preview.Two" / "Preview.Two.mkv", 5)
    make(tmp_path / "packed.mkv", 14)
    (src / "Packed.Three").mkdir()
    subprocess.run([SEVENZ, "a", "-mx0", str(src / "Packed.Three" / "packed.7z"), str(tmp_path / "packed.mkv")],
                   check=True, capture_output=True)  # fmt: skip
    (src / "Music.Keep").mkdir()
    for i in range(10):
        (src / "Music.Keep" / f"track{i}.mp3").write_bytes(b"\0" * 2048)

    before = sorted(p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file())
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"min_sample_size_mb": 1, "log_folder": str(tmp_path / "logs")}))

    _plan_result, planned = _run(src, dst, config, "--dry-run")
    report_file = tmp_path / "report.jsonl"
    result, live = _run(src, dst, config, "--report", str(report_file))
    assert result.returncode == 0, result.stdout[-2000:]

    by_path = {}
    for item in live["items"]:
        assert item["path"] not in by_path, f"duplicate item for {item['path']}"
        by_path[item["path"]] = item
    for rel in before:
        assert rel in by_path, f"no terminal action for {rel}"
        assert by_path[rel]["action"] in ("moved", "deleted", "extracted", "kept", "skipped", "blocked")

    assert by_path["Movie.One/Movie.One.mkv"]["action"] == "moved"
    assert by_path["Movie.One/Movie.One.mkv"]["destination"].endswith("Movie.One.mkv")
    assert by_path["Movie.One/Movie.One.nfo"]["action"] == "deleted"
    assert by_path["Preview.Two/Preview.Two.mkv"]["reason_code"] == "video_too_short"
    assert by_path["Packed.Three/packed.7z"]["action"] == "extracted"
    assert by_path["Music.Keep/track0.mp3"]["action"] == "kept"
    assert live["item_counts"]["moved"] == 2  # Movie.One plus the video extracted from Packed.Three

    planned_by_path = {i["path"]: i for i in planned["items"]}
    for rel in before:
        assert planned_by_path[rel]["planned"] is True
        assert planned_by_path[rel]["action"] == by_path[rel]["action"], rel

    lines = [json.loads(line) for line in report_file.read_text().splitlines()]
    assert lines[-1]["type"] == "summary" and lines[-1]["status"] == "completed"
    assert sum(1 for line in lines if line["type"] == "item") == len(live["items"])
